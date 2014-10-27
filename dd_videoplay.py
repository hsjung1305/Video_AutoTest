import argparse
import commands
import glob
import HTML
import logging
import os
import re
import sys
import time

test_name = 'dd_video'
curdir = os.path.realpath(os.path.dirname(__file__))

TARGET_MEDIA_PATH = '/sdcard/mediafiles'
TARGET_IMAGE_PATH = '/sdcard/images'
HOST_MEDIA_PATH = './cts'
HOST_IMAGE_PATH = './images'

# Drop ratio 15% to determine playback result
kDropLimit = 15

parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('--times', dest='times', metavar='Secs', type=int, nargs='+',
                    help='times for video playback')
args = parser.parse_args()

logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    logging.debug('Process main....')
    isConnectADB()
    install()
    run()
    uninstall()
    return True

def run(run_options=None):
    logging.debug('Process run......')

    f = open('videoplayback_result.html', 'w')

    file_list = glob.glob('%s/*' % HOST_MEDIA_PATH)

    result_list = {}

    for file in file_list:
        baseFile = os.path.basename(file)
        result_list[baseFile] = ['N/A', 'N/A', 'N/A', 'N/A', '-1', 'N/A', 'N/A', 'N/A']

    num = 1
    sortedResult = []
    for file in file_list:
        testID = 'Video-%d' % num
        baseFile = os.path.basename(file)
        runEachTest(testID, baseFile, result_list[baseFile])
        sortedResult.append(result_list[baseFile])
        time.sleep(2)
        num += 1

    htmlcode = HTML.table(sortedResult,
                          header_row=['Test ID', 'File Name', 'Codec Type',
                                      'Video Size', 'FPS', 'Frame Drop',
                                      'Playback Result', 'Screen Capture'])

    os.system('adb shell input keyevent KEYCODE_HOME')

    f.write(htmlcode)
    f.close()

    return True

def runEachTest(testID='', file='', result={}):
    logging.debug('Process runEachTest......')

    # result : Test ID | File Name | Codec Type | Video Size | FPS |
    #          Frame Drop | Result | Screen Capture
    result[0] = testID
    result[1] = file
    file = file.replace('(', '\(')
    file = file.replace(')', '\)')

    logging.debug(file)

    getDuration = 'ffprobe %s/%s 2>&1 | grep Duration' % (HOST_MEDIA_PATH, file)

    logging.debug(os.popen(getDuration).read())
    durationChecker = re.compile(r'.*(\d{2}):(\d{2}):(\d{2}).*')
    checkedDuration = durationChecker.match(os.popen(getDuration).read())

    if checkedDuration is None:
        playResult = '<font color="red">NG</font>'
        return False

    duration = int(checkedDuration.group(1))*3600 +\
               int(checkedDuration.group(2))*60 + int(checkedDuration.group(3))

    if (args.times[0] > duration):
        logging.warning('Capture time is bigger than duration of mediafiles.')
        logging.warning('Capture time : %d secs, Mediafile duration : %d secs'\
               % (args.times[0], duration))
        logging.warning('You need to reduce capture time')
        playResult = '<font color="red">NG</font>'
        return False

    logging.debug('Duration : %d' % duration)

    getMetadata = 'ffprobe %s/%s 2>&1 | grep Video' % (HOST_MEDIA_PATH, file)
    metadataChecker = re.compile(r'.*Video: (?P<codec>\w+).*'\
                                 '\s(?P<size>\d+x\d+).*\s(?P<fps>(\d+|\d+\.\d+)) fps.*')
    metadata = metadataChecker.match(os.popen(getMetadata).read())

    result[2] = metadata.group('codec')
    result[3] = metadata.group('size')
    result[4] = metadata.group('fps')

    logging.debug('Codec : %s' % metadata.group('codec'))
    logging.debug('Size : %s' % metadata.group('size'))
    logging.debug('FPS : %s' % metadata.group('fps'))

    getPkgInfo = 'adb shell pm list packages | grep gallery'
    pkgChecker = re.compile(r'package:(?P<pkg_name>.*gallery3d).*')
    pkgName = pkgChecker.match(os.popen(getPkgInfo).read())

    os.system('adb shell am start -t video/* -d %s/%s'\
              ' -n %s/com.android.gallery3d.app.MovieActivity'\
              % (TARGET_MEDIA_PATH, os.path.basename(file), pkgName.group('pkg_name')))

    time.sleep(args.times[0]/2)
    os.system('adb shell /system/bin/screencap -p %s/%s.png'\
              % (TARGET_IMAGE_PATH, testID))
    os.system('adb pull %s/%s.png %s'\
              % (TARGET_IMAGE_PATH, testID, HOST_IMAGE_PATH))
    result[7] = image('%s/%s.png' % (HOST_IMAGE_PATH, testID))

    time.sleep(args.times[0]/2)
    getFrameInfo = 'adb shell dumpsys media.player | grep VideoFramesDecoded'
    getFrame = os.popen(getFrameInfo).read()
    frameChecker = re.compile(r'.*Decoded\((?P<decode>\d+)'\
                              '.*Dropped\((?P<drop>\d+).*')
    checkedFrame = frameChecker.match(getFrame)

    if checkedFrame is None:
        playResult = '<font color="red">NG</font>'
        os.system('adb shell input keyevent KEYCODE_MOVE_END')
        os.system('adb shell input keyevent KEYCODE_ENTER')
        result[6] = playResult
        return False

    droppedFrame = int(checkedFrame.group('drop'))
    totalFrame = droppedFrame + int(checkedFrame.group('decode'))

    if (totalFrame != 0):
        dropRatio = droppedFrame * 100 / totalFrame
    else:
        playResult = '<font color="red">NG</font>'
        result[6] = playResult
        return False

    if (dropRatio > kDropLimit):
        playResult = '<font color="red">NG</font>'
    else:
        playResult = 'OK'


    result[5] = '%d%% (%d/%d)' % (dropRatio, droppedFrame, totalFrame)
    result[6] = playResult

    logging.debug(testID)
    for item in result:
        logging.debug(item)

    os.system('adb shell input keyevent KEYCODE_BACK')
    os.system('adb shell input keyevent KEYCODE_BACK')

    return True

def image(url, width=None, height=None):
    if (width == None or height == None):
        width = "180px"
        height = "320px"
    return '<img src="%s" width="%s" height="%s" align="center"></a>'\
           % (url, width, height)

def isConnectADB():
    kNoDevice = 27
    adbCmd = 'adb devices'
    adbResult = os.popen(adbCmd)
    countAdb = adbResult.read()

    if len(countAdb) <= kNoDevice:
        logging.error('No ADB connection !')
        sys.exit(1)
    logging.info("ADB Connceted !")

def install(install_options=None):
    logging.debug('Process install.....')
    os.system('adb shell mkdir %s' % TARGET_MEDIA_PATH)
    os.system('adb shell mkdir %s' % TARGET_IMAGE_PATH)
    os.system('adb push %s/%s/ %s' % (curdir, HOST_MEDIA_PATH, TARGET_MEDIA_PATH))

def uninstall(uninstall_option=None):
    logging.debug('Process uninstall.....')
    os.system('adb shell rm -rf %s' % TARGET_MEDIA_PATH)
    os.system('adb shell rm -rf %s' % TARGET_IMAGE_PATH)

if __name__ == '__main__':
    main()
    sys.exit(0)

