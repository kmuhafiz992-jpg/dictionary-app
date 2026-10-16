# Pocket Lexicon (offline)

An Android dictionary for English, Hindi, Marathi and Urdu that works with no internet. Built for reading books.

- Type, paste or select a word. You get the English meaning (with examples and synonyms) and the word in Hindi, Marathi and Urdu, with a Roman-letter pronunciation guide.
- Works from any of the four languages. Look up a Hindi, Marathi or Urdu word and you get its English meaning and the matching word in the other languages.
- Listen buttons read words and meanings aloud with three voice styles and three speeds.
- Select a word in your book app and choose Pocket Lexicon from the text menu, or use Share > Pocket Lexicon.
- Paste a whole sentence and tap any word in it to look it up.

The app has no internet permission. All word data is packed inside the APK when GitHub builds it.

## Build the APK on GitHub

1. Create a free GitHub account and a new repository. This part works best on a computer.
2. Unzip the file and upload everything to the repository, including the `tools` folder. If the hidden `.github` folder doesn't upload, choose Add file > Create new file, type `.github/workflows/build.yml` as the name, and paste in the contents of `github-workflow-build.yml`.
3. Open the Actions tab and wait for "Build APK" to finish. The first run downloads the dictionary data, so allow 10 to 20 minutes.
4. Open the finished run. Download `PocketLexicon-APK`, unzip it, and install `app-debug.apk` on your phone. Android will ask you to allow installs from your browser or file manager.
5. After installing, you can turn the phone's internet off. Nothing in the app needs it.

If the build fails, copy the error from the Actions tab and send it back. The `data-report` download on the same run shows how many words each language got.

## Voices for offline listening

Voices come from your phone's text-to-speech engine. For listening without internet, download the voice data while you are online: Settings > Text-to-speech (or Language and input) > Google Text-to-speech > Install voice data > Hindi, Marathi, Urdu. If a voice is marked "(needs internet)" in the app, it will not speak offline.

## Where the words come from

- English meanings, examples and synonyms: Princeton WordNet 3.0 (through the nltk package).
- Hindi, Marathi and Urdu words and romanization: Wiktionary, through the kaikki.org extracts (CC BY-SA). English glosses are reversed to get English-to-Hindi/Marathi/Urdu words, so a few matches can be rough and some words have no match.
