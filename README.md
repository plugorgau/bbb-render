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

You may also want to install the Pitivi video editor to tweak the
result before rendering:

```
sudo apt install pitivi
```

## Downloading a presentation

The first script will download the presentation assets locally:

```
./download.py presentation_url outdir
```

The `presentation_url` should be a full URL containing the string
`/playback/presentation/2.0/playback.html?meetingId=`.  This will
download the presentation metadata, video footage and slides.


## Create a GES project

The second script combines the downloaded assets into a GStreamer
Editing Services project.

```
./make-xges.py outdir presentation.xges
```

In addition to being viewable in Pitivi, the project can be previewed
using the following command:

```
ges-launch-1.0 --load presentation.xges
```

Currently it incorporates the following aspects of the recording:

* [x] Slides
* [x] Screensharing video
* [x] Webcam video+audio

Not handled:

* [ ] Mouse cursor
* [ ] Whiteboard scribbles
* [ ] Text chat


## Render Video

If everything looks good, the project can be rendered to a video.  The
following should produce an mp4 file suitable for upload to YouTube:

```
ges-launch-1.0 --load presentation.xges -o presentation.mp4 \
  --format 'video/quicktime,variant=iso:video/x-h264,profile=high:audio/mpeg,mpegversion=4,base-profile=lc'
```

Or alternatively, render as WebM:

```
ges-launch-1.0 --load presentation.xges -o presentation.webm \
  --format 'video/webm:video/x-vp8:audio/x-vorbis'
```
