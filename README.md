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
sudo apt install python3-gi gir1.2-ges-1.0 ges1.0-tools python3-intervaltree
```

You may also want to install the [Pitivi video
editor](http://www.pitivi.org/) to tweak the result before rendering:

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

It takes the following optional parameters to influence the project:

* `--start=TIME` and `--end=TIME` can be used to trim footage from the start or end of the recording.  This can be helpful if the recording was started early, or you want to split the recoridng into multiple projects.
* `--width=WIDTH` and `--height=HEIGHT` control the dimensions of the video.  The default resolution is 1920x1080.
* `--webcam-size=PERCENT` controls how much of the frame width will be devoted to the webcam footage.  This defaults to 20%.
* `--stretch-webcam` stretches the webcam footage by 33%.  This was added to correct the camera aspect ratio in some of our recordings.
* `--backdrop=FILE` sets a still image to place behind other elements.  This can be used to fill in the empty space in the frame.
* `--opening-credits=FILE[:DURATION]` and `--closing-credits=FILE[:DURATION]` will add credits to project.  These can either be videos or still images (which will default to 3 seconds duration).  These options can be repeated to add multiple credits.
* `--annotations` will include whiteboard annotations and red dot cursor to slides.
* `--fullscreen` shows slides or screenshare in fullscreen and webcam over it.

Some accepted `TIME` formats:

* `ss` seconds (example: 1500 or 1500.3)
* `mm:ss` minutes and seconds
* `hh:mm:ss` hours minutes and seconds
* `dd:hh:mm:ss` days, hours, minutes and seconds

Currently the project includes the following aspects of the BBB
recording:

* [x] Slides
* [x] Screensharing video
* [x] Webcam video+audio
* [x] Mouse cursor
* [x] Whiteboard scribbles (excluding text)

It does not cover:

* [ ] Text chat

The project can be previewed using the `ges-launch-1.0` command line tool:

```
ges-launch-1.0 --load presentation.xges
```

It can also be loaded in Pitivi if you want to tweak the project
before rendering.

## Render Video

If everything looks good, the project can be rendered to a video.  The
following should produce an MP4 file suitable for upload to YouTube:

```
ges-launch-1.0 --load presentation.xges -o presentation.mp4
```

Or alternatively, it can be rendered as WebM:

```
ges-launch-1.0 --load presentation.xges -o presentation.webm \
  --format 'video/webm:video/x-vp8:audio/x-vorbis'
```

## License

Copyright (c) 2020-2021 [James Henstridge](https://github.com/jhenstridge) and contributors

The project is Free as in freedom software, released under the terms of the MIT License.

See the LICENSE file.
