#!/usr/bin/python3

import argparse
import os
import sys
import xml.etree.ElementTree as ET

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GES', '1.0')
from gi.repository import GLib, GObject, Gst, GES


def file_to_uri(path):
    path = os.path.realpath(path)
    return 'file://' + path


class Presentation:

    def __init__(self, basedir):
        self.basedir = basedir
        self.timeline = GES.Timeline.new_audio_video()

        # Get the timeline's two tracks
        self.video_track, self.audio_track = self.timeline.get_tracks()
        if self.video_track.type == GES.TrackType.AUDIO:
            self.video_track, self.audio_track = self.audio_track, self.video_track
        self.project = self.timeline.get_asset()
        self._assets = {}

        # Construct the presentation
        self.add_webcams()
        self.add_slides()
        self.add_deskshare()

    def _get_asset(self, path):
        asset = self._assets.get(path)
        if asset is None:
            asset = GES.UriClipAsset.request_sync(
                file_to_uri(os.path.join(self.basedir, path)))
            self.project.add_asset(asset)
            self._assets[path] = asset
        return asset

    def _set_dimensions(self, clip, posx, posy, width, height):
        for element in clip.find_track_elements(self.video_track, GES.TrackType.VIDEO, GObject.TYPE_NONE):
            element.set_child_property("posx", posx)
            element.set_child_property("posy", posy)
            element.set_child_property("width", width)
            element.set_child_property("height", height)

    def add_webcams(self):
        layer = self.timeline.append_layer()
        asset = self._get_asset('video/webcams.webm')
        clip = layer.add_asset(asset, 0, 0, asset.props.duration, GES.TrackType.UNKNOWN)
        self._set_dimensions(clip, 1280, 600, 640, 480)
        #self._set_dimensions(clip, 960, 480, 320, 240)

    def add_slides(self):
        layer = self.timeline.append_layer()
        doc = ET.parse(os.path.join(self.basedir, 'shapes.svg'))
        for img in doc.iterfind('.//{http://www.w3.org/2000/svg}image'):
            path = img.get('{http://www.w3.org/1999/xlink}href')
            # If this is a "deskshare" slide, don't show anything
            if path.endswith('/deskshare.png'):
                continue

            start = float(img.get('in')) * Gst.SECOND
            end = float(img.get('out')) * Gst.SECOND
            x = int(img.get('x'))
            y = int(img.get('y'))
            width = int(img.get('width'))
            height = int(img.get('height'))

            asset = self._get_asset(path)
            clip = layer.add_asset(asset, start, 0, end - start, GES.TrackType.VIDEO)
            self._set_dimensions(clip, 0, 0, 1280, 720)

    def add_deskshare(self):
        layer = self.timeline.append_layer()
        asset = self._get_asset('deskshare/deskshare.webm')
        duration = asset.props.duration
        doc = ET.parse(os.path.join(self.basedir, 'deskshare.xml'))
        for event in doc.iterfind('./event'):
            start = float(event.get('start_timestamp')) * Gst.SECOND
            end = float(event.get('stop_timestamp')) * Gst.SECOND
            # Trim event to duration of video
            if start > duration: continue
            end = min(end, duration)

            clip = layer.add_asset(asset, start, start, end - start - 1, GES.TrackType.UNKNOWN)
            self._set_dimensions(clip, 0, 0, 1280, 720)

    def save(self, filename):
        self.project.save(self.timeline, file_to_uri(filename), None, True)


def main(argv):
    parser = argparse.ArgumentParser(description='convert a BigBlueButton presentation into a GES project')
    parser.add_argument('basedir', metavar='PRESENTATION-DIR', type=str,
                        help='directory containing BBB presentation assets')
    parser.add_argument('project', metavar='OUTPUT', type=str,
                        help='output filename for GES project')
    args = parser.parse_args(argv[1:])
    Gst.init(None)
    GES.init()
    p = Presentation(args.basedir)
    p.save(args.project)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
