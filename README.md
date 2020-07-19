# BigBlueButton Presentation Renderer

The BigBlueButton web conferencing system provides the ability to
record meetings.  Rather than producing a single video file though, it
produces multiple assets (webcam footage, screenshare footage, slides,
scribbles, chat, etc) and relies on a web player to assemble them.

This project provides some scripts to download the assets for a
recorded presentation, and assemble them into a single video suitable
for archive or upload to other video hosting sites.


## Prerequisites

The scripts are written in Python, and rely on the GStreamer Editing
Services libraries.  On an Ubuntu 20.04 system, you will need to
install at least the following:

```
sudo apt install python3-gi gir1.2-ges-1.0 ges1.0-tools
```


## Downloading a presentation

The first script will download the presentation assets locally:

```
./download.py presentation_url outdir
```

The `presentation_url` should be a full URL containing the string
`/playback/presentation/2.0/playback.html?meetingId=`.  This will
download the presentation metadata, video footage and slides.
