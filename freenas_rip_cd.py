#!/usr/local/bin/python
from datetime import datetime
import glob
import os
import re
import readline
import subprocess
import tempfile


"""
iTunes does a decent enough job at ripping CDs into one's iTunes library, but
who's got an optical drive connected to their Mac these days?  I don't.  I do,
however, have one in my FreeNAS system, so that's what I want to use to rip
CDs.  This script does a decent enough job at that.  It first uses cdda2wav to
rip the CD to a series of .wav files (using the -cddb flag to get disc and
track info).  It then uses lame to convert the .wav files to .mp3s.  The final
result is a directory in /tmp with mp3s, with a folder and filename structure
that matches the metadata from CDDB.  Which is more or less what iTunes would
have done.
"""


def _rl_input(prompt, prefill=''):
    readline.set_startup_hook(lambda: readline.insert_text(prefill))
    try:
        return raw_input(prompt)
    finally:
        readline.set_startup_hook()


def main(prompt_for_disc_and_song_title_changes=True):

    start_time = datetime.utcnow()
    print '***\nStarting at %s' % start_time
    TMPDIR = '/tmp'
    BASEDIR = tempfile.mkdtemp(dir=TMPDIR)
    print '***\nCreated BASEDIR "%s"' % BASEDIR
    BASEDIR_WAV = os.path.join(BASEDIR, 'wav')
    BASEDIR_MP3 = os.path.join(BASEDIR, 'mp3')
    os.mkdir(BASEDIR_WAV)
    os.mkdir(BASEDIR_MP3)

    print '***\nStarting cdda2wav'
    subprocess.check_call('cd %s && sudo cdda2wav -alltracks -cddb 1' % BASEDIR_WAV, shell=True)

    # if any problems (much slower):
    # sudo cdda2wav -alltracks -cddb 1 -paranoia

    disc_info = {}
    songs = {}   # song_num -> song_name
    cddb_filename = os.path.join(BASEDIR_WAV, 'audio.cddb')
    if os.path.isfile(cddb_filename):
        print '***\nCDDB filename is %s' % cddb_filename
        with open(cddb_filename, 'rb') as cddb_file:
            for line in cddb_file:
                if not disc_info.get('disc_title'):
                    try:
                        # e.g.,: 'DTITLE=Pearl Jam - Eddie Vedder / "Into The Wild" Soundtrack'
                        disc_info['disc_title'] = re.findall(r'DTITLE=(.*)', line)[0]
                        continue
                    except IndexError:
                        pass
                if not disc_info.get('year'):
                    try:
                        disc_info['year'] = re.findall(r'DYEAR=(.*)', line)[0]
                        continue
                    except IndexError:
                        pass
                if not disc_info.get('genre'):
                    try:
                        disc_info['genre'] = re.findall(r'DGENRE=(.*)', line)[0]
                        continue
                    except IndexError:
                        pass
                try:
                    # e.g.,: 'TTITLE0=Setting Forth'
                    song_num, song_name = re.findall(r'TTITLE(\d*)=(.*)', line)[0]
                    songs[int(song_num) + 1] = song_name  # song_num is 0-based, but the files are named 1-based
                except IndexError:
                    pass

        # Based on this: 'Pearl Jam - Eddie Vedder / "Into The Wild" Soundtrack'
        m = re.match(r'(.*) / (.*)', disc_info.get('disc_title'))
        if m:
            disc_info['artist'], disc_info['album'] = m.groups()

    else:
        # We don't have a CDDB file, so we don't have any of this info
        disc_info['disc_title'] = ''
        disc_info['year'] = ''
        disc_info['genre'] = ''
        disc_info['artist'] = ''
        disc_info['album'] = ''
        songs = {}
        for song_num, filename in enumerate(glob.glob('%s/*.wav' % BASEDIR_WAV), start=1):
            songs[song_num] = ''

    # Remove double-quotes and slashes from any of the fields, so that they don't cause
    # problems in, e.g., file names
    for v in ('disc_title', 'year', 'genre', 'artist', 'album'):
        existing_val = disc_info.get(v)
        disc_info[v] = existing_val.replace('"', '').replace('/', ' - ') \
                       if existing_val is not None else None
    for song_num in songs.keys():
        songs[song_num] = songs[song_num].replace('"', '').replace('/', '')

    print '*** Disc tile ***\n%s' % disc_info.get('disc_title')
    print 'Artist: %s' % disc_info.get('artist')
    print 'Album: %s' % disc_info.get('album')
    print 'Year: %s' % disc_info.get('year')
    print 'Genre: %s' % disc_info.get('genre')
    resp = ''
    while prompt_for_disc_and_song_title_changes and not resp in ('Y', 'N', 'YES', 'NO'):
        resp = _rl_input('\nMake any changes? (Y/N) ', prefill='N').upper().strip()
    if resp in ('Y', 'YES'):
        confirmed = False
        while not confirmed:
            disc_info['artist'] = _rl_input('Artist: ', prefill=disc_info.get('artist'))
            disc_info['album'] = _rl_input('Album: ', prefill=disc_info.get('album'))
            disc_info['year'] = _rl_input('Year: ', prefill=disc_info.get('year'))
            disc_info['genre'] = _rl_input('Genre: ', prefill=disc_info.get('genre'))
            confirmed = _rl_input('Confirmed? (Y/N) ', prefill='Y').upper().strip() in ('Y', 'YES')

    print '*** Songs ***\n%s' % '\n'.join('%s: %s' % (num, name) for num, name in songs.items())
    resp = ''
    while prompt_for_disc_and_song_title_changes and not resp in ('Y', 'N', 'YES', 'NO'):
        resp = _rl_input('\nMake any changes? (Y/N) ', prefill='N').upper().strip()
    if resp in ('Y', 'YES'):
        confirmed = False
        while not confirmed:
            for num, name in songs.items():
                songs[num] = _rl_input('%d: ' % num, prefill=songs[num])
            confirmed = _rl_input('Confirmed? (Y/N) ', prefill='Y').upper().strip() in ('Y', 'YES')

    numsongs = len(songs)
    for songnum, songname in songs.items():
        songname_wav = os.path.join(BASEDIR_WAV, 'audio_%.2d.wav' % songnum)
        songname_mp3 = os.path.join(BASEDIR_MP3, '%.2d %s.mp3' % (songnum, songname))
        # iTunes, when it imports a CD, uses an .mp3 encoder with 160 kbps ("high quality")
        # here, we use lame's "Fixed bit rate jstereo 128 kbps encoding, highest quality (recommended)"
        subprocess.check_call('lame -h "%s" "%s" ' % (songname_wav, songname_mp3) + \
              '--tt "%s" --ta "%s" --tl "%s" ' % (songname, disc_info.get('artist'), disc_info.get('album')) + \
              '--ty "%s" --tn "%s/%s" --tg "%s"' % (disc_info.get('year'), songnum, numsongs, disc_info.get('genre')),
              shell=True)

    print '***\nDone ripping the CD into %s' % BASEDIR
    if disc_info.get('artist') and disc_info.get('album'):
        album_dirname = os.path.join(TMPDIR, disc_info.get('artist'), disc_info.get('album'))
        print '***\nRestructuring %s as %s' % (BASEDIR, album_dirname)
        if not os.path.exists(album_dirname):
            os.makedirs(album_dirname)
        for song_file in glob.glob('%s/*' % BASEDIR_MP3):
            subprocess.check_call('mv "%s" "%s"' % (song_file, album_dirname), shell=True)
        subprocess.check_call('rm -rf "%s"' % BASEDIR_WAV, shell=True)
        subprocess.check_call('rmdir "%s" "%s"' % (BASEDIR_MP3, BASEDIR), shell=True)

    end_time = datetime.utcnow()
    print '***\nDone at %s (%s elapsed)' % (end_time, end_time - start_time)


if __name__ == '__main__':
    main(prompt_for_disc_and_song_title_changes=False)
