package com.pocketlexicon.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Locale;
import java.util.Set;

/**
 * Pocket Lexicon: a WebView that shows assets/index.html. This app has no internet permission.
 * The page gets two things from here: the phone's text-to-speech voices and the clipboard.
 * Text shared or selected in other apps is passed to the page too.
 */
public class MainActivity extends Activity {

    private WebView web;
    private TextToSpeech tts;
    private volatile boolean ttsReady = false;
    private boolean pageLoaded = false;
    private String pendingText = null;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(false);
        s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);

        web.addJavascriptInterface(new Bridge(), "AndroidBridge");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pageLoaded = true;
                deliverPending();
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                // Only the app's own pages are shown here. Anything else is handed to another app.
                if ("file".equals(u.getScheme())) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                }
                return true;
            }
        });

        tts = new TextToSpeech(getApplicationContext(), new TextToSpeech.OnInitListener() {
            @Override
            public void onInit(int status) {
                if (status != TextToSpeech.SUCCESS) return;
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override
                    public void onStart(String id) {
                        ttsEvent(id, "start");
                    }

                    @Override
                    public void onDone(String id) {
                        ttsEvent(id, "done");
                    }

                    @Override
                    public void onError(String id) {
                        ttsEvent(id, "error");
                    }

                    @Override
                    public void onError(String id, int errorCode) {
                        ttsEvent(id, "error");
                    }

                    @Override
                    public void onStop(String id, boolean interrupted) {
                        ttsEvent(id, "stop");
                    }
                });
                ttsReady = true;
            }
        });

        handleIntent(getIntent());
        web.loadUrl("file:///android_asset/index.html");
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
        deliverPending();
    }

    @Override
    protected void onDestroy() {
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        if (web != null) web.destroy();
        super.onDestroy();
    }

    private void handleIntent(Intent i) {
        if (i == null) return;
        String action = i.getAction();
        CharSequence t = null;
        if (Intent.ACTION_PROCESS_TEXT.equals(action)) {
            t = i.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
        } else if (Intent.ACTION_SEND.equals(action)) {
            t = i.getCharSequenceExtra(Intent.EXTRA_TEXT);
        }
        if (t != null && t.toString().trim().length() > 0) pendingText = t.toString();
    }

    private void deliverPending() {
        if (pageLoaded && pendingText != null) {
            String t = pendingText;
            pendingText = null;
            js("window.__incoming && window.__incoming(" + JSONObject.quote(t) + ")");
        }
    }

    private void js(final String script) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (web != null) web.evaluateJavascript(script, null);
            }
        });
    }

    private void ttsEvent(String id, String ev) {
        js("window.__tts && window.__tts('" + id + "','" + ev + "')");
    }

    private void doSpeak(String id, String text, String voiceName, String langTag, float rate, float pitch) {
        if (!ttsReady) {
            ttsEvent(id, "error");
            return;
        }
        tts.stop();
        boolean voiceSet = false;
        if (voiceName != null && voiceName.length() > 0) {
            Set<Voice> all = tts.getVoices();
            if (all != null) {
                for (Voice v : all) {
                    if (v.getName().equals(voiceName)) {
                        voiceSet = tts.setVoice(v) == TextToSpeech.SUCCESS;
                        break;
                    }
                }
            }
        }
        if (!voiceSet) {
            int r = tts.setLanguage(Locale.forLanguageTag(langTag));
            if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                ttsEvent(id, "nolang");
                return;
            }
        }
        tts.setSpeechRate(rate);
        tts.setPitch(pitch);
        int res = tts.speak(text, TextToSpeech.QUEUE_FLUSH, new Bundle(), id);
        if (res != TextToSpeech.SUCCESS) ttsEvent(id, "error");
    }

    /** Methods the page can call as window.AndroidBridge.* */
    private class Bridge {

        @JavascriptInterface
        public String getVoices(String code) {
            JSONArray arr = new JSONArray();
            try {
                if (!ttsReady || code == null) return "[]";
                Set<Voice> vs = tts.getVoices();
                if (vs == null) return "[]";
                for (Voice v : vs) {
                    Locale l = v.getLocale();
                    if (l != null && code.equals(l.getLanguage())) {
                        JSONObject o = new JSONObject();
                        o.put("name", v.getName());
                        o.put("lang", l.toLanguageTag());
                        o.put("net", v.isNetworkConnectionRequired());
                        arr.put(o);
                    }
                }
            } catch (Exception ignored) {
            }
            return arr.toString();
        }

        @JavascriptInterface
        public void speak(final String id, final String text, final String voiceName,
                          final String langTag, final float rate, final float pitch) {
            final String safeId = id == null ? "0" : id.replaceAll("[^0-9]", "");
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    doSpeak(safeId, text, voiceName, langTag, rate, pitch);
                }
            });
        }

        @JavascriptInterface
        public void stop() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (tts != null) tts.stop();
                }
            });
        }

        @JavascriptInterface
        public void copy(final String text) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Pocket Lexicon", text));
                }
            });
        }

        @JavascriptInterface
        public String paste() {
            try {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null && cm.hasPrimaryClip()) {
                    ClipData d = cm.getPrimaryClip();
                    if (d != null && d.getItemCount() > 0) {
                        CharSequence t = d.getItemAt(0).coerceToText(MainActivity.this);
                        return t == null ? "" : t.toString();
                    }
                }
            } catch (Exception ignored) {
            }
            return "";
        }
    }
}
