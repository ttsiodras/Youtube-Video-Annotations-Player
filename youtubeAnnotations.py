#!/usr/bin/env python2

import os
import re
import sys
import time
import signal
import subprocess
from lxml import etree
from xml.sax.saxutils import unescape

# mplayer's bmovl filter is currently (2012/03) borked;
# you need to apply a patch from here:
#
#   http://users.softlab.ntua.gr/~ttsiod/patch.bmovl.gz
#
# (see discussion about MPlayer bug here:
#  http://lists.mplayerhq.hu/pipermail/mplayer-users/2012-March/084300.html)
mplayer = '/usr/local/bin/mplayer.bmovl.patched'


def panic(x, color=True):
    if not x.endswith("\n"):
        x += "\n"
    if color:
        sys.stderr.write("\n"+chr(27)+"[32m")
    sys.stderr.write(x)
    if color:
        sys.stderr.write(chr(27) + "[0m\n")
    sys.exit(1)


def mysystem(cmd):
    if 0!=os.system(cmd):
        panic("Failed to execute:\n"+cmd)


class Matcher:
    def __init__(self, pattern, flags=0):
        self._pattern = re.compile(pattern, flags)
        self._lastOne = None

    def match(self, line):
        self._match=re.match(self._pattern, line)
        self._lastOne='Match'
        return self._match

    def search(self, line):
        self._search=re.search(self._pattern, line)
        self._lastOne='Search'
        return self._search

    def group(self, idx):
        if self._lastOne == 'Match':
            return self._match.group(idx)
        elif self._lastOne == 'Search':
            return self._search.group(idx)
        else:
            return panic("Matcher group called with index %d before match/search!\n" % idx)


def getTime(annotationTime, m=[Matcher(r'(\d):(\d\d):(\d\d).(\d)')]):
    if not m[0].match(annotationTime):
        panic("Unexpected time value: " + annotationTime)
    ho, mi, se, d = float(m[0].group(1)), float(m[0].group(2)), float(m[0].group(3)), float(m[0].group(4))
    return 3600.*ho + 60.*mi + se + d*0.10


def parseAnnotations(filename):
    class Annotation:
        pass
    annotations = {}
    a=etree.parse(open(filename))
    root=a.getroot()
    if len(root)<1 or root.tag != "document":
        panic("You must use an XML file that contains Youtube annotations.")
    for t in root.xpath("annotations/annotation/TEXT"):
        ann = t.getparent()
        regions = ann.xpath("segment/movingRegion/anchoredRegion")
        a = Annotation()
        a._t0 = regions[0].get('t')
        a._t1 = regions[1].get('t')
        for attr in ['sx', 'sy', 'x', 'y', 'w', 'h']:
            setattr(a, '_'+attr, float(regions[0].get(attr)))
        a._text = etree.tostring(t, pretty_print=True)
        a._text = unescape(a._text).replace("<TEXT>", "").replace("</TEXT>", "")
        annotations[a._t0] = a
    return annotations


def DetectVideoSizeAndLength(filename):
    try:
        cmd = mplayer + ' -quiet -identify -frames 0 -vo null "%s"' % filename
        cmd += ' 2>/dev/null | grep ID_VIDEO'
        attrs = ['width', 'height', 'fps']
        attrsCast = [int, int, float]
        for line in os.popen(cmd).readlines():
            for attr, cast in zip(attrs, attrsCast):
                uAttr = attr.upper()
                if 'ID_VIDEO_'+uAttr in line:
                    locals()[attr] = cast(line.split('=')[1].strip())
        return [locals()[x] for x in attrs]
    except:
        panic("Failed to identify video's attributes with " + mplayer)


def CreateFifoAndSpawnMplayer():
    if os.path.exists("bmovl"):
        os.unlink("bmovl")
    os.mkfifo("bmovl")
    cmd = mplayer+" -nocorrect-pts -vo x11 -quiet -vf bmovl=0:0:./bmovl"
    cmd += " \"%s\"" % sys.argv[2]
    return subprocess.Popen(cmd, shell=True)


def CreateAnnotationImage(annotation, width, height):
    #print annotation._t0, '-', annotation._t1, ':',
    #print annotation._sy, annotation._sx, annotation._y, annotation._x, annotation._h, annotation._w
    #print "In", nextTimeInSeconds
    #print annotation._text
    open("tmp", "w").write(annotation._text)
    cmd = 'convert'
    cmd += ' -trim '
    ww, hh = int(width*annotation._w/100.), int(height*annotation._h/100.)
    cmd += ' -size %dx%d' % (ww, hh)
    pointsize = int(height/25)
    cmd += ' -pointsize %d' % pointsize
    cmd += ' -depth 8 -fill black -background orange'
    cmd += ' caption:@tmp line.png'
    mysystem(cmd)
    mysystem("convert -bordercolor orange -border 15 line.png annotation.png ; rm line.png")
    mysystem("convert annotation.png -fill gray50 -colorize '100%' -raise 8 -normalize -blur 0x4 light.png")
    mysystem("convert annotation.png light.png -compose hardlight -composite  finalAnnotation.png")
    os.rename("finalAnnotation.png", "line.png")
    for f in ["tmp", "light.png", "annotation.png"]:
        os.unlink(f)


def SendAnnotationImageToFIFO(annotation, width, height, fifoToMplayer, m=[Matcher(r'PNG (\d+)x(\d+) ')]):
    dimensions = os.popen("identify line.png").readlines()[0]
    if not m[0].search(dimensions):
        panic("Failed to create annotation image...")
    w, h = int(m[0].group(1)), int(m[0].group(2))
    x, y = int(width*annotation._x/100.), int(height*annotation._y/100.)
    mysystem("convert line.png line.rgb")
    data = open("line.rgb").read()
    fifoToMplayer.write("RGB24 %d %d %d %d 0 1\n" % (w, h, x, y))
    fifoToMplayer.write(data)
    fifoToMplayer.flush()
    return (w, h, x, y)


def SendClearBufferToFIFO(fifoToMplayer, renderArea):
    w, h, x, y = renderArea
    fifoToMplayer.write("CLEAR %d %d %d %d\n" % (w, h, x, y))


def SleepAndCheckMplayer(childMPlayer, dt):
    if None != childMPlayer.poll():
        return False

    def OopsWeAreDead(_, __):
        pass
    # setup a signal that will interrupt the sleep if the child (MPlayer) dies
    oldSignal = signal.signal(signal.SIGCHLD, OopsWeAreDead)
    if dt>0.:
        time.sleep(dt)
    signal.signal(signal.SIGCHLD, oldSignal)
    if None != childMPlayer.poll():
        return False
    return True


def main():
    if len(sys.argv) != 3 or not os.path.isfile(sys.argv[1]) or not os.path.isfile(sys.argv[2]):
        helpMsg = "Usage: "+os.path.basename(sys.argv[0])+" <filename.xml> <videoFilename>\n"
        helpMsg += '''
For example, for my VIM video, at: http://www.youtube.com/watch?v=o0BgAp11C9s

- To get the videoFilename, just use 'youtube-dl'
  (http://rg3.github.com/youtube-dl/). Use it like this:

    youtube-dl 'http://www.youtube.com/watch?v=o0BgAp11C9s'

  This will store the video data as 'o0BgAp11C9s.flv'

- To get the .xml file, simply...

    wget -O whatever.xml 'http://www.youtube.com/annotations_auth/read2?feat=TCS&video_id=VIDEO_ID

  ...where your VIDEO_ID is the part of the link after the '=',
  e.g. 'o0BgAp11C9s' for my VIM video.

Enjoy!

P.S. If it doesn't work with your video, learn Python, fork on GitHub,
and fix it yourself - this was just a quick hack :-)
'''
        panic(helpMsg, False)
    width, height, fps = DetectVideoSizeAndLength(sys.argv[2])
    childMPlayer = CreateFifoAndSpawnMplayer()
    annotations = parseAnnotations(sys.argv[1])
    startTime = time.time()
    fifoToMplayer = open("bmovl", "w")
    for bt in sorted(annotations.keys()):
        annotation = annotations[bt]
        nextTimeInSeconds = getTime(annotation._t0)
        CreateAnnotationImage(annotation, width, height)
        currentTime = time.time()
        if not SleepAndCheckMplayer(childMPlayer, startTime+nextTimeInSeconds-currentTime):
            break
        renderArea = SendAnnotationImageToFIFO(annotation, width, height, fifoToMplayer)
        nextTimeInSeconds = getTime(annotation._t1)
        currentTime = time.time()
        if not SleepAndCheckMplayer(childMPlayer, startTime+nextTimeInSeconds-currentTime):
            break
        SendClearBufferToFIFO(fifoToMplayer, renderArea)
    try:
        childMPlayer.kill()
    except:
        pass
    for f in ["line.rgb", "line.png", "tmp", "bmovl"]:
        if os.path.exists(f):
            os.unlink(f)

if __name__ == "__main__":
    main()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
