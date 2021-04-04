#!/usr/bin/python3

import argparse
import collections
import operator
import os
import sys
import xml.etree.ElementTree as ET

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
gi.require_version('GES', '1.0')
from gi.repository import GLib, GObject, Gst, GstPbutils, GES
from intervaltree import IntervalTree

# GStreamer's content detection doesn't work well with ElementTree's
# automatically assigned namespace prefixes.
ET.register_namespace("", "http://www.w3.org/2000/svg")


SlideInfo = collections.namedtuple('SlideInfo', ['id', 'width', 'height', 'start', 'end'])
CursorEvent = collections.namedtuple('CursorEvent', ['x', 'y', 'timestamp'])


def file_to_uri(path):
    path = os.path.realpath(path)
    return 'file://' + path


class Presentation:

    def __init__(self, opts):
        self.opts = opts
        self.cam_width = round(opts.width * opts.webcam_size / 100)
        self.slides_width = opts.width - self.cam_width

        self.timeline = GES.Timeline.new_audio_video()

        # Get the timeline's two tracks
        self.video_track, self.audio_track = self.timeline.get_tracks()
        if self.video_track.type == GES.TrackType.AUDIO:
            self.video_track, self.audio_track = self.audio_track, self.video_track
        self.project = self.timeline.get_asset()
        self._assets = {}

        # Construct the presentation
        self.set_track_caps()
        self.set_project_metadata()
        self.add_credits()
        self.add_webcams()
        self.add_cursor()
        self.add_slides(self.opts.annotations)
        self.add_deskshare()
        self.add_backdrop()

    def _add_layer(self, name):
        layer = self.timeline.append_layer()
        layer.register_meta_string(GES.MetaFlag.READWRITE, 'video::name', name)
        return layer

    def _get_asset(self, path):
        asset = self._assets.get(path)
        if asset is None:
            asset = GES.UriClipAsset.request_sync(file_to_uri(path))
            self.project.add_asset(asset)
            self._assets[path] = asset
        return asset

    def _get_dimensions(self, asset):
        info = asset.get_info()
        video_info = info.get_video_streams()[0]
        return (video_info.get_width(), video_info.get_height())

    def _constrain(self, dimensions, bounds):
        width, height = dimensions
        max_width, max_height = bounds
        new_height = round(height * max_width / width)
        if new_height <= max_height:
            return max_width, new_height
        return round(width * max_height / height), max_height

    def _add_clip(self, layer, asset, start, inpoint, duration,
                  posx, posy, width, height, trim_end=True):
        if trim_end:
            # Skip clips entirely after the end point
            if start > self.end_time:
                return
            # Truncate clips that go past the end point
            duration = min(duration, self.end_time - start)

        # Skip clips entirely before the start point
        if start + duration < self.start_time:
            return
        # Rewrite start, inpoint, and duration to account for time skip
        start -= self.start_time
        if start < 0:
            duration += start
            if not asset.is_image():
                inpoint += -start
            start = 0

        # Offset start point by the length of the opening credits
        start += self.opening_length

        clip = layer.add_asset_full(asset, start, inpoint, duration,
                                    GES.TrackType.UNKNOWN)
        for element in clip.find_track_elements(
                self.video_track, GES.TrackType.VIDEO, GObject.TYPE_NONE):
            element.set_child_property("posx", posx)
            element.set_child_property("posy", posy)
            element.set_child_property("width", width)
            element.set_child_property("height", height)

    def set_track_caps(self):
        # Set frame rate and audio rate based on webcam capture
        asset = self._get_asset(
            os.path.join(self.opts.basedir, 'video/webcams.webm'))
        info = asset.get_info()

        video_info = info.get_video_streams()[0]
        self.video_track.props.restriction_caps = Gst.Caps.from_string(
            'video/x-raw(ANY), width=(int){}, height=(int){}, '
            'framerate=(fraction){}/{}'.format(
                self.opts.width, self.opts.height,
                video_info.get_framerate_num(),
                video_info.get_framerate_denom()))

        audio_info = info.get_audio_streams()[0]
        self.audio_track.props.restriction_caps = Gst.Caps.from_string(
            'audio/x-raw(ANY), rate=(int){}, channels=(int){}'.format(
                audio_info.get_sample_rate(), audio_info.get_channels()))

        # Set start and end time from options
        self.start_time = round(self.opts.start * Gst.SECOND)
        if self.opts.end is None:
            self.end_time = asset.props.duration
        else:
            self.end_time = round(self.opts.end * Gst.SECOND)

        # Offset for the opening credits
        self.opening_length = 0

        # Add an encoding profile for the benefit of Pitivi
        profile = GstPbutils.EncodingContainerProfile.new(
            'MP4', 'bbb-render encoding profile',
            Gst.Caps.from_string('video/quicktime,variant=iso'))
        profile.add_profile(GstPbutils.EncodingVideoProfile.new(
            Gst.Caps.from_string('video/x-h264,profile=high'), None,
            self.video_track.props.restriction_caps, 0))
        profile.add_profile(GstPbutils.EncodingAudioProfile.new(
            Gst.Caps.from_string('audio/mpeg,mpegversion=4,base-profile=lc'),
            None, self.audio_track.props.restriction_caps, 0))
        self.project.add_encoding_profile(profile)

    def set_project_metadata(self):
        doc = ET.parse(os.path.join(self.opts.basedir, 'metadata.xml'))
        name = doc.find('./meta/name')
        if name is not None:
            self.project.register_meta_string(
                GES.MetaFlag.READWRITE, 'name', name.text.strip())

    def add_webcams(self):
        layer = self._add_layer('Camera')
        asset = self._get_asset(
            os.path.join(self.opts.basedir, 'video/webcams.webm'))
        dims = self._get_dimensions(asset)
        if self.opts.stretch_webcam:
            dims = (dims[0] * 16/12, dims[1])
        width, height = self._constrain(
            dims, (self.cam_width, self.opts.height))

        self._add_clip(layer, asset, 0, 0, asset.props.duration,
                       self.opts.width - width, 0,
                       width, height)

    def add_slides(self, with_annotations):
        layer = self._add_layer('Slides')
        doc = ET.parse(os.path.join(self.opts.basedir, 'shapes.svg'))
        slides = {}
        for img in doc.iterfind('./{http://www.w3.org/2000/svg}image[@class="slide"]'):
            info = SlideInfo(
                id=img.get('id'),
                width=int(img.get('width')),
                height=int(img.get('height')),
                start=round(float(img.get('in')) * Gst.SECOND),
                end=round(float(img.get('out')) * Gst.SECOND),
            )
            slides[info.id] = info

            # Don't bother creating an asset for out of range slides
            if info.end < self.start_time or info.start > self.end_time:
                continue

            path = img.get('{http://www.w3.org/1999/xlink}href')
            # If this is a "deskshare" slide, don't show anything
            if path.endswith('/deskshare.png'):
                continue

            asset = self._get_asset(os.path.join(self.opts.basedir, path))
            width, height = self._constrain(
                self._get_dimensions(asset),
                (self.slides_width, self.opts.height))
            self._add_clip(layer, asset, info.start, 0, info.end - info.start,
                           0, 0, width, height)

        # If we're not processing annotations, then we're done.
        if not with_annotations:
            return

        layer = self._add_layer('Annotations')
        # Move above the slides layer
        self.timeline.move_layer(layer, layer.get_priority() - 1)
        for canvas in doc.iterfind('./{http://www.w3.org/2000/svg}g[@class="canvas"]'):
            info = slides[canvas.get('image')]
            t = IntervalTree()
            for index, shape in enumerate(canvas.iterfind('./{http://www.w3.org/2000/svg}g[@class="shape"]')):
                shape.set('style', shape.get('style').replace(
                    'visibility:hidden;', ''))
                timestamp = round(float(shape.get('timestamp')) * Gst.SECOND)
                undo = round(float(shape.get('undo')) * Gst.SECOND)
                if undo < 0:
                    undo = info.end

                # Clip timestamps to slide visibility
                start = min(max(timestamp, info.start), info.end)
                end = min(max(undo, info.start), info.end)

                # Don't bother creating annotations for out of range times
                if end < self.start_time or start > self.end_time:
                    continue

                t.addi(start, end, [(index, shape)])

            t.split_overlaps()
            t.merge_overlaps(strict=True, data_reducer=operator.add)
            for index, interval in enumerate(sorted(t)):
                svg = ET.Element('{http://www.w3.org/2000/svg}svg')
                svg.set('version', '1.1')
                svg.set('width', '{}px'.format(info.width))
                svg.set('height', '{}px'.format(info.height))
                svg.set('viewBox', '0 0 {} {}'.format(info.width, info.height))

                for _, shape in sorted(interval.data):
                    svg.append(shape)

                path = os.path.join(
                    self.opts.basedir,
                    'annotations-{}-{}.svg'.format(info.id, index))
                with open(path, 'wb') as fp:
                    fp.write(ET.tostring(svg, xml_declaration=True))

                asset = self._get_asset(path)
                width, height = self._constrain(
                    (info.width, info.height),
                    (self.slides_width, self.opts.height))
                self._add_clip(layer, asset, interval.begin, 0, interval.end - interval.begin,
                               0, 0, width, height)

    def add_cursor(self):
        layer = self._add_layer('Cursor')
        dot = self._get_asset('dot.png')
        dot_width, dot_height = self._get_dimensions(dot)

        doc = ET.parse(os.path.join(self.opts.basedir, 'cursor.xml'))
        events = []
        for event in doc.iterfind('./event'):
            x, y = event.find('./cursor').text.split()
            timestamp = round(float(event.attrib['timestamp']) * Gst.SECOND)
            events.append(CursorEvent(float(x), float(y), timestamp))

        # Cursor positions are relative to the size of the current slide
        doc = ET.parse(os.path.join(self.opts.basedir, 'shapes.svg'))
        slides = []
        for img in doc.iterfind('./{http://www.w3.org/2000/svg}image'):
            start = round(float(img.get('in')) * Gst.SECOND)
            end = round(float(img.get('out')) * Gst.SECOND)
            width = int(img.get('width'))
            height = int(img.get('height'))
            slides.append(SlideInfo(None, width, height, start, end))

        for i, pos in enumerate(events):
            # negative positions are used to indicate that no cursor
            # should be displayed.
            if pos.x < 0 and pos.y < 0:
                continue

            # Show cursor until next event or if it is the last event,
            # the end of recording.
            if i + 1 < len(events):
                end = events[i + 1].timestamp
            else:
                end = self.end_time

            # Find the width/height of the slide corresponding to this
            # point in time
            while len(slides) > 1 and slides[1].start <= start:
                del slides[0]
            width, height = self._constrain(
                (slides[0].width, slides[0].height),
                (self.slides_width, self.opts.height))

            self._add_clip(layer, dot, pos.timestamp, 0, end - pos.timestamp,
                           round(width*pos.x - dot_width/2),
                           round(height*pos.y - dot_height/2), dot_width, dot_height)

    def add_deskshare(self):
        doc = ET.parse(os.path.join(self.opts.basedir, 'deskshare.xml'))
        events = doc.findall('./event')
        if len(events) == 0:
            return

        layer = self._add_layer('Deskshare')
        asset = self._get_asset(
            os.path.join(self.opts.basedir, 'deskshare/deskshare.webm'))
        width, height = self._constrain(self._get_dimensions(asset),
                                        (self.slides_width, self.opts.height))
        duration = asset.props.duration
        for event in events:
            start = round(float(event.get('start_timestamp')) * Gst.SECOND)
            end = round(float(event.get('stop_timestamp')) * Gst.SECOND)
            # Trim event to duration of video
            if start > duration: continue
            end = min(end, duration)

            self._add_clip(layer, asset, start, start, end - start,
                           0, 0, width, height)

    def add_backdrop(self):
        if not self.opts.backdrop:
            return
        layer = self._add_layer('Backdrop')
        asset = self._get_asset(self.opts.backdrop)
        self._add_clip(layer, asset, 0, 0, self.end_time,
                       0, 0, self.opts.width, self.opts.height)

    def add_credits(self):
        if not (self.opts.opening_credits or self.opts.closing_credits):
            return

        layer = self._add_layer('credits')
        for fname in self.opts.opening_credits:
            duration = None
            if ':' in fname:
                fname, duration = fname.rsplit(':', 1)
                duration = round(float(duration) * Gst.SECOND)

            asset = self._get_asset(fname)
            if duration is None:
                if asset.is_image():
                    duration = 3 * Gst.SECOND
                else:
                    duration = asset.props.duration

                    dims = self._get_dimensions(asset)

            dims = self._get_dimensions(asset)
            width, height = self._constrain(
                dims, (self.opts.width, self.opts.height))

            self._add_clip(layer, asset, 0, 0, duration,
                           0, 0, width, height, trim_end=False)
            self.opening_length += duration

        closing_length = 0
        for fname in self.opts.closing_credits:
            duration = None
            if ':' in fname:
                fname, duration = fname.rsplit(':', 1)
                duration = round(float(duration) * Gst.SECOND)

            asset = self._get_asset(fname)
            if duration is None:
                if asset.is_image():
                    duration = 3 * Gst.SECOND
                else:
                    duration = asset.props.duration

                    dims = self._get_dimensions(asset)

            dims = self._get_dimensions(asset)
            width, height = self._constrain(
                dims, (self.opts.width, self.opts.height))

            self._add_clip(layer, asset, self.end_time + closing_length, 0,
                           duration, 0, 0, width, height, trim_end=False)
            closing_length += duration

    def save(self):
        self.timeline.commit_sync()
        self.timeline.save_to_uri(file_to_uri(self.opts.project), None, True)


def main(argv):
    parser = argparse.ArgumentParser(description='convert a BigBlueButton presentation into a GES project')
    parser.add_argument('--start', metavar='SECONDS', type=float, default=0,
                        help='Seconds to skip from the start of the recording')
    parser.add_argument('--end', metavar='SECONDS', type=float, default=None,
                        help='End point in the recording')
    parser.add_argument('--width', metavar='WIDTH', type=int, default=1920,
                        help='Video width')
    parser.add_argument('--height', metavar='HEIGHT', type=int, default=1080,
                        help='Video height')
    parser.add_argument('--webcam-size', metavar='PERCENT', type=int,
                        default=25, choices=range(100),
                        help='Amount of screen to reserve for camera')
    parser.add_argument('--stretch-webcam', action='store_true',
                        help='Stretch webcam to 16:9 aspect ratio')
    parser.add_argument('--backdrop', metavar='FILE', type=str, default=None,
                        help='Backdrop image for the project')
    parser.add_argument('--opening-credits', metavar='FILE[:DURATION]',
                        type=str, action='append', default=[],
                        help='File to use as opening credits (may be repeated)')
    parser.add_argument('--closing-credits', metavar='FILE[:DURATION]',
                        type=str, action='append', default=[],
                        help='File to use as closing credits (may be repeated)')
    parser.add_argument('--annotations', action='store_true', default=False,
                        help='Add annotations to slides (requires inkscape)')
    parser.add_argument('basedir', metavar='PRESENTATION-DIR', type=str,
                        help='directory containing BBB presentation assets')
    parser.add_argument('project', metavar='OUTPUT', type=str,
                        help='output filename for GES project')
    opts = parser.parse_args(argv[1:])
    Gst.init(None)
    GES.init()
    p = Presentation(opts)
    p.save()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
