# Jips

Jips is an audio server for Japanese word pronunciations.

It is designed for use with the [Yomitan](https://yomitan.wiki/) pop-up
dictionary but also works with other immesion learning tools, including
[Memento](https://github.com/ripose-jp/Memento).

## Why use a (local) audio server?

Yomitan comes built in with the ability to retrieve audio from online sources,
including JapanesePod101, Jisho and Wiktionary.

So why use a seperate audio server?

The trouble is that these audio sources are not great.  They have sound issues,
for clicks and reverb that will drive you nuts when you include the audio on a
mined card in Anki.  They are slow to load - breaking your focus when you're
concentrating on some difficult Japanese.  And they have incomplete coverage.

Jips is designed to improve on all of this.

## Features

1. Jips is easy to run
   - Just place the dictionary files and run `docker compose up -d`
2. Jips is simple
   - Doesn't try to run from within Anki
     - this is not necessary as people create their cards outside anki and then add them via ankiconnect
   - Uses standard HTTP libaries for Python
     - Flask, Gunicorn, etc, super duper boring stuff
3. Jips is fast
   - does well over 1000 requests per second
     - so lookups are instant
     - no rewrite-in-rust is necessary
   - [TODO] and sets HTTP cache headers correctly so that browsers cache the audio
4. Jips is high quality
   - complete test suite
   - static analysis
   - conforms to Yomitans own json schema
5. Jips has massive coverage
   - with common community dictionaries Jips can cover Xk words
   - more than enough for your Japanese learning journey

## Getting up and running

### Starting Jips

1. Check out repo
2. Place dictionary files into `./dicts`
   - for copyright reasons these are distributed [elsewhere](https://github.com/aramrw/yomichan_audio_server/releases)
3. `docker compose up --build -d`

Then try it out by visiting this url:

    http://localhost:1989/audio.json?term=%E6%97%A5%E6%9C%AC&reading=%E3%81%AB%E3%81%BB%E3%82%93

### Configuring Yomitan

Inside Yomitan's settings, under `Audio` > `Configure audio playback sources`
add the following url as `Custom URL (JSON)`:

    http://localhost:1989/audio.json?term={term}&reading={reading}

Jips needs both the Kanji and the reading to unambigiously locate the
appropriate audio in dictionaries.

![Yomitan configuration](assets/yomitan-config.png)
