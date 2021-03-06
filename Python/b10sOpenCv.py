#!/usr/bin/env python

import cv2
import sys, time
import numpy as np
import sc
from threading import Thread
from Camera import Camera

try:
    import RPi.GPIO as GPIO
except Exception as e:
    class GPIO():
        BCM = 0
        OUT = 0
        @staticmethod
        def setmode(sp):
            pass
        @staticmethod
        def setup(p, v):
            pass
        @staticmethod
        def cleanup():
            pass
        @staticmethod
        def output(p, v):
            pass

FPS = 20.0
LOOP_PERIOD = 1.0/FPS

CAM_RES = (160, 120)

TENS_FREQ = 80
TENS_PERIOD = 1.0/TENS_FREQ

POWS = (4,27,18,24)
GPIOS = (17,22,23,25)
TENS_LEN = len(GPIOS)
powVals = [1]*TENS_LEN
gpioVals = [0]*TENS_LEN

(SB,XB,YB) = (0,0,0)
(SH,XH,YH) = (0,0,0)
cascadeDetected = 0
blobDetected = 0
FPA = 0.5
FPB = 1.0-FPA

def setup():
    global prevFrame, frame, mCamera
    global mDetector, mCascade
    global POWS, GPIOS, powVals, gpioVals
    global mSynth

    sc.start()
    mSynth = sc.Synth("fmSynth")
    #mSynth = sc.Synth("PMCrotale")

    GPIO.setmode(GPIO.BCM)
    for pin in (POWS+GPIOS):
        GPIO.setup(pin, GPIO.OUT)

    mCamera = Camera(CAM_RES)
    mCamera.update()

    frame = cv2.blur(cv2.cvtColor(mCamera.frame, cv2.COLOR_RGB2GRAY), (4,4))
    prevFrame = frame

    # Setup SimpleBlobDetector parameters.
    mParams = cv2.SimpleBlobDetector_Params()
    mParams.minThreshold = 16;
    mParams.maxThreshold = 32;
    mParams.filterByArea = True
    mParams.minArea = 64
    mParams.maxArea = 10e3
    mParams.filterByConvexity = True
    mParams.minConvexity = 0.001
    mParams.filterByInertia = True
    mParams.minInertiaRatio = 0.001

    mDetector = cv2.SimpleBlobDetector(mParams)
    mCascade = None

    if len(sys.argv) > 1:
        mCascade = cv2.CascadeClassifier(sys.argv[1])
    else:
        print "Please provide a cascade file if you want to do face/body detection."

def loop():
    global prevFrame, frame, mCamera
    global mDetector, mCascade
    global POWS, GPIOS, powVals, gpioVals
    global SH,XH,YH, SB,XB,YB, cascadeDetected, blobDetected
    global mSynth

    prevFrame = frame

    mCamera.update()

    frameU = cv2.cvtColor(mCamera.frame, cv2.COLOR_RGB2GRAY)
    frame = cv2.blur(frameU, (4,4))
    diffFrame = cv2.absdiff(frame, prevFrame)

    ret, diffFrameThresh = cv2.threshold(diffFrame, 32, 255, cv2.THRESH_BINARY_INV)
    blobs = []
    blobs = mDetector.detect(diffFrameThresh)

    powVals = [1]*TENS_LEN
    gpioVals = [0]*TENS_LEN

    (s,x,y) = (0,0,0)
    blobDetected *= 0.9
    numBlobs = len(blobs)
    # average blobs
    for blob in blobs:
        (s,x,y) = (s+blob.size, x+blob.pt[0], y+blob.pt[1])

    if (numBlobs > 0):
        (s,x,y) = ((s/numBlobs), x/numBlobs, y/numBlobs)
        (SB,XB,YB) = (FPA*SB+FPB*s, FPA*XB+FPB*x, FPA*YB+FPB*y)
        # set up pulses
        (XBN, YBN) = (XB/CAM_RES[0], YB/CAM_RES[1])
        pulseLocationIndex = int(XBN*2)+2*int(YBN*2)
        powVals[pulseLocationIndex] = 0
        gpioVals[pulseLocationIndex] = 1

        #set up Synth
        mSynth.freq1 = 150*XBN+250
        mSynth.freq2 = 5*YBN+1
        blobDetected = 10.0

        #another Synth
        #mSynth.midi = XBN
        #mSynth.art = 1*YBN
        #mSynth.tone = 6*XBN+4

    mSynth.amp = blobDetected

    if mCascade is not None:
        cascadeResult = []
        if (time.time()%5 > 4):
            cascadeResult = mCascade.detectMultiScale(
                frameU,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(16, 16),
                flags=cv2.cv.CV_HAAR_SCALE_IMAGE)

        # get cascade detector results and update (size, x, y)
        cascadeDetected *= 0.8
        (s,x,y) = (0,0,0)
        if len(cascadeResult) > 0:
            cascadeDetected = 2.0
        for (x0, y0, w0, h0) in cascadeResult:
            if(w0 > s):
                (s,x,y) = (w0, x0, y0)
        if cascadeDetected > 1.0:
            (SH,XH,YH) = (FPA*SH+FPB*s, FPA*XH+FPB*x, FPA*YH+FPB*y)

    # Display the resulting frame
    #cv2.imshow('_', cv2.drawKeypoints(diffFrameThresh, blobs, np.array([]), (0,0,255), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS))

    if cv2.waitKey(1) & 0xFF == ord('q'):
        cleanUp()
        sys.exit(0)

def cleanUp():
    global mCamera, mSynth
    mSynth.free()
    sc.quit()
    mCamera.release()
    GPIO.cleanup()
    cv2.destroyAllWindows()

if __name__=="__main__":
    lastLoop = 0
    tensWaveVal = 0
    calcTens = True

    def upTWV():
        global tensWaveVal
        while(calcTens is True):
            tensWaveVal = int((time.time()/TENS_PERIOD)%2)
            time.sleep(TENS_PERIOD)

    t = Thread(target=upTWV)
    t.start()
    setup()
    try:
        while True:
            GPIO.output(POWS, tuple([tensWaveVal*v for v in powVals]))
            GPIO.output(GPIOS, tuple([tensWaveVal*v for v in gpioVals]))

            now = time.time()
            if (now-lastLoop > LOOP_PERIOD):
                lastLoop = now
                loop()
                print "%s"%(1.0/(time.time()-lastLoop))
    except Exception as e:
        print e
        cleanUp()
        calcTens = False
        time.sleep(1)
        t.join(1)
