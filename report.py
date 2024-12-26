import pytz
from datetime import datetime
import json
import os
import math
import sys

TIMEZONE = pytz.timezone('US/Mountain')
MAX_HIST_COUNT = 40

class Keystroke(object):
    def __init__(self, timestamp, key):
        self.time = datetime.fromtimestamp(timestamp, TIMEZONE)
        self.key = key

    def to_dict(self):
        return {
            'time': self.time.isoformat(),
            'key': self.key,
        }

def convert_size(size_bytes):
    """ Source: https://stackoverflow.com/questions/5194057/better-way-to-convert-file-sizes-in-python """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

def get_keystrokes(filename='/var/log/keylogger.log'):
    print('Opening: %s' % filename)
    print('File size: %s' % convert_size(os.path.getsize(filename)))
    print()

    keystrokes = []
    with open(filename, 'r') as f:
        for line in f:
            time = int(line[:10])
            key = line[13:-1]
            keystrokes.append(Keystroke(time, key))
    return keystrokes

def compute_frequences(keystrokes):
    freq = {}
    for keystroke in keystrokes:
        if not keystroke.key in freq:
            freq[keystroke.key] = 0
        freq[keystroke.key] += 1
    return freq

def print_statistics(keystrokes):
    start_time = min(ks.time for ks in keystrokes)
    end_time = max(ks.time for ks in keystrokes)

    print('WPM: %.1f' % compute_wpm(keystrokes))
    print('Start time: %s' % start_time.isoformat())
    print('End time: %s' % end_time.isoformat())
    print('Duration: %s' % (end_time - start_time))
    print('Number keystrokes: %d' % len(keystrokes))
    print('Unique keys used: %d' % len(set(ks.key for ks in keystrokes)))

def print_histogram(frequencies, max_limit=None):
    sorted_frequencies = sorted(frequencies.items(), key=lambda f: f[1], reverse=True)

    if max_limit is None:
        max_limit = len(sorted_frequencies)
    else:
        sorted_frequencies = sorted_frequencies[:max_limit]

    max_item_length = max(len(x[0]) for x in sorted_frequencies)
    max_freq_length = len(str(max(x[1] for x in sorted_frequencies)))
    max_freq_value = max(x[1] for x in sorted_frequencies)
    hist_scaling_factor = MAX_HIST_COUNT / max_freq_value

    format = '%' + str(max_item_length) + 's -> %' + str(max_freq_length) + 'd '

    print('HISTOGRAM: Top %d values' % max_limit)
    for item, freq in sorted_frequencies:
        print((format % (item, freq)) + '*' * int(freq * hist_scaling_factor))

    print('Legend: * = %f keys' % (1 / hist_scaling_factor))

def json_serialize(keystrokes, to_filename):
    with open(to_filename, mode='w') as f:
        json.dump({
            'startTime': min(ks.time for ks in keystrokes).isoformat(),
            'endTime': max(ks.time for ks in keystrokes).isoformat(),
            'keyStrokes': [ks.to_dict() for ks in keystrokes],
        }, f, indent=4)

def write_plaintext(keystrokes, to_filename):
    shift = False
    with open(to_filename, mode='w') as f:
        for ks in keystrokes:
            if len(ks.key) == 1:
                f.write(ks.key.upper() if shift else ks.key)
            elif ks.key == '[return]':
                f.write('\n')
def convert_to_char(key):
    match key:
        case  "[tab]": return "\t"
        case "[return]" : return "\n"
        case _ : return key

def compute_time_per_char(keystrokes):
    # keystrokes should be time ordered
    time = {}
    first = ''
    last_keystroke = None
    for keystroke in keystrokes:
        if first == '':
            first = keystroke.key
            last_keystroke = keystroke
            continue
        if not keystroke.key in time:
            time[keystroke.key] = 0
        time[keystroke.key] += min(keystroke.time - last_keystroke.time, 5) # assume breaks longer than 5 secs are not a typing problem

    frequencies = compute_frequences(keystrokes)
    
    for key in time:
        time[key] = time[key]/frequencies[key]

    return time

def compute_deletions_per_char(keystrokes):
    # make adjusted string with [right] and [left]
    # keystrokes should be time ordered
    # TODO account for ^, v, and clicks.
    start = []
    end = []
    for ks in keystrokes:
        if ks.key == "[left]":
            if len(start) == 0:
                continue
            end = [start[-1]] + end
            start = start[:-1]
        elif ks.key == "[right]":
            if len(end) == 0:
                continue
            start = start + [end[0]]
            end = end[1:]
        else:
            # do not add [right-ctr] and such
            start = start + [ks.key]
    
    
    ordered_keystrokes = start + end
    del_count = {}
    del_bank = 0
    for i in range(len(ordered_keystrokes)-1,1,-1):
        key = ordered_keystrokes[i]
        last_key = ordered_keystrokes[i-1]
        if key == "[del]":
            del_bank += 1
        elif del_bank > 0:
            if not last_key in del_count:
                del_count[last_key] = 0
            del_count[last_key] += 1
            del_bank -= 1
    return del_count

def compute_wpm(keystrokes):
    # keystrokes should be time ordered
    word_count = 0
    total_time = 0 # seconds
    assert len(keystrokes) > 1
    pause_time = False
    for i in range(1,len(keystrokes)):
        ks = keystrokes[i]
        last_ks = keystrokes[i-1]
        if convert_to_char(ks.key).isspace() and not convert_to_char(last_ks.key).isspace() :
            word_count += 1
        if ks.key == ".":
            pause_time = True
        if not pause_time: 
            total_time += min((ks.time - last_ks.time).total_seconds(), 5.0)
        if convert_to_char(ks.key).isalpha():
            pause_time = False
    return word_count/total_time * 60

if __name__ == '__main__':
    if len(sys.argv) == 2:
        filename = sys.argv[1]
    else:
        print('Usage: python report.py [filename]')
        exit(1)
    if not os.path.isfile(filename):
        print('Error: "%s" is not a file.' % filename)
        exit(1)

    keystrokes = get_keystrokes(filename)
    frequencies = compute_frequences(keystrokes)
    delete_frequencies = compute_deletions_per_char(keystrokes)

    print('*** REPORT ***')
    print()

    print_statistics(keystrokes)
    print()

    print_histogram(delete_frequencies, max_limit=20)
    print()



    # json_serialize(keystrokes, 'out/pramod.json')
    # write_plaintext(keystrokes, 'out/pramod.txt')