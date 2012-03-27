Read my [blog post for details about this](http://ttsiodras.github.com/youtube.html): It allows you to playback Youtube videos with their annotations, offline
(via MPlayer). In what follows, change 'o0BgAp11C9s' to whatever your
Youtube video id is (the last part of the Youtube video URL).

1. You download your video from youtube (via [youtube-dl](http://rg3.github.com/youtube-dl/)):

    $ youtube-dl -o vimPower.flv 'http://www.youtube.com/watch?v=o0BgAp11C9s'

2. You then download the video's annotation data:

    $ wget -O annotations.xml 'http://www.youtube.com/annotations_auth/read2?feat=TCS&video_id=o0BgAp11C9s'

3. Then you run my tiny Python script:

    $ youtubeAnnotations.py annotations.xml vimPower.flv

The script then...

* creates the MPlayer's bmovl filter FIFO
* spawns a [patched MPlayer](http://ttsiodras.github.com/patch.bmovl.gz) (due to a bmovl [bug](http://lists.mplayerhq.hu/pipermail/mplayer-users/2012-March/084269.html)!) as a child process, with the required arguments for the <tt>bmovl</tt> filter
* starts keeping track of playback time, and based on the anchoredRegions timestamps...
* creates bitmaps from the TEXT regions via ImageMagick
* and sends them over to the MPlayer's bmovl FIFO for displaying

The script worked fine for my [VIM](http://ttsiodras.github.com/myvim.html#vimeovim) video, and I have also tested it on a few other Youtube videos. You can also see the results in a [full-HD version of the same video](http://www.mediafire.com/file/ge1imhbivswsixr/Vim.C.and.C++.flv). If you do decide to use this script, please remember that you must also [patch](http://ttsiodras.github.com/patch.bmovl.gz) your MPlayer, since the <tt>bmovl</tt> filter is currently (2012/03) broken.

Enjoy!

NAVIGATE
