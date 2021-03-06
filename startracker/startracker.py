# startracker.py
# by Umair Khan, from the Portland State Aerospace Society
# based on OpenStarTracker from Andrew Tennenbaum at the University of Buffalo
# openstartracker.org

# Imports - built-ins
import sys
import time
import threading
import glob
import random
import logging

# Imports - external
import numpy as np
import cv2
from pydbus.generic import signal
from pydbus import SystemBus
from gi.repository import GLib
from systemd import journal

# Imports - back-end
import beast

# Set up systemd logger
# modified from https://medium.com/@trstringer/logging-to-systemd-in-python-45150662440a
logger = logging.getLogger("org.OreSat.StarTracker")
journald_handler = journal.JournalHandler()
journald_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
logger.addHandler(journald_handler)
logger.setLevel(logging.DEBUG)

# CUSTOM DEBUG VARIABLES
DEBUG_ENABLED = True
STACK_LAYERS = 0

# Solver
class StarTracker:

    # Initialize everything
    def __init__(self):

        # Prepare constants
        self.P_MATCH_THRESH = 0.99
        self.YEAR = 1991.25
        self.SAMPLE_DIR = None
        self.MEDIAN_IMAGE = None
        self.S_DB = None
        self.SQ_RESULTS = None
        self.S_FILTERED = None
        self.C_DB = None

    # Startup sequence
    def startup(self, median_path, config_path, db_path, sample_dir = None):

        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.startup")
            STACK_LAYERS = STACK_LAYERS + 1

        # Set the sample directory
        logger.info("Beginning startup sequence...")
        self.SAMPLE_DIR = sample_dir

        # Prepare star tracker
        self.MEDIAN_IMAGE = cv2.imread(median_path)
        logger.info("Loaded median image from {}".format(median_path))
        beast.load_config(config_path)
        logger.info("Loaded configuration from {}".format(config_path))
        self.S_DB = beast.star_db()
        self.S_DB.load_catalog(db_path, self.YEAR)
        logger.info("Loaded star database from {}".format(db_path))
        self.SQ_RESULTS = beast.star_query(self.S_DB)
        self.SQ_RESULTS.kdmask_filter_catalog()
        self.SQ_RESULTS.kdmask_uniform_density(beast.cvar.REQUIRED_STARS)
        self.S_FILTERED = self.SQ_RESULTS.from_kdmask()
        logger.info("Filtered stars")
        self.C_DB = beast.constellation_db(self.S_FILTERED, 2 + beast.cvar.DB_REDUNDANCY, 0)
        logger.info("Startup sequence complete!")

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.startup")

    # Capture an image, or pull one from the sample directory
    def capture(self):

        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.capture")
            STACK_LAYERS = STACK_LAYERS + 1

        # Pull from sample directory
        if self.SAMPLE_DIR != None:
            path = random.choice(glob.glob(self.SAMPLE_DIR + "*"))

            if(DEBUG_ENABLED):
                STACK_LAYERS = STACK_LAYERS - 1
                print(f"{STACK_LAYERS * ' '}End StarTracker.capture")

            return path, cv2.imread(path)

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.capture")

        # Capture an image
        return None, None

    # See if an image is worth attempting to solve
    def preprocess(self, img):

        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.preprocess")
            STACK_LAYERS = STACK_LAYERS + 1

        # Generate test parameters
        height, width, channels = img.shape
        total_pixels = height * width
        blur_check = int(total_pixels * 0.99996744)
        too_many_check = int(total_pixels * 0.99918619)

        # Convert and threshold the image
        img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        ret, threshold = cv2.threshold(img, 80, 255, cv2.THRESH_BINARY)

        # Count the number of black pixels in the thresholded image
        threshold_black = total_pixels - cv2.countNonZero(threshold)

        # Check the test values and return appropriate value
        if threshold_black > blur_check:
            blur = cv2.Laplacian(img, cv2.CV_64F).var()
            if blur != 0 and blur < 5:
                return "image too blurry"
            else:
                return "image contains too few stars"
            return 1
        elif threshold_black < too_many_check:
            return "unsuitable image"

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.preprocess")

        return "good"

    # Solution function
    def solve(self, orig_img):

        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.solve")
            STACK_LAYERS = STACK_LAYERS + 1

        # Keep track of solution time
        starttime = time.time()

        # Create and initialize variables
        img_stars = beast.star_db()
        match = None
        fov_db = None

        # Process the image for solving
        img = np.clip(orig_img.astype(np.int16) - self.MEDIAN_IMAGE, a_min = 0, a_max = 255).astype(np.uint8)
        img_grey = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Remove areas of the image that don't meet our brightness threshold and then extract contours
        ret, thresh = cv2.threshold(img_grey, beast.cvar.THRESH_FACTOR * beast.cvar.IMAGE_VARIANCE, 255, cv2.THRESH_BINARY)
        contours, hierarchy = cv2.findContours(thresh, 1, 2);

        # Process the contours
        for c in contours:

            M = cv2.moments(c)

            if M["m00"] > 0:

                # this is how the x and y position are defined by cv2
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]

                # see https://alyssaq.github.io/2015/computing-the-axes-or-orientation-of-a-blob/ for how to convert these into eigenvectors/values
                u20 = M["m20"] / M["m00"] - cx ** 2
                u02 = M["m02"] / M["m00"] - cy ** 2
                u11 = M["m11"] / M["m00"] - cx * cy

                # The center pixel is used as the approximation of the brightest pixel
                img_stars += beast.star(cx - beast.cvar.IMG_X / 2.0, cy - beast.cvar.IMG_Y / 2.0, float(cv2.getRectSubPix(img_grey, (1,1), (cx,cy))[0,0]), -1)

        # We only want to use the brightest MAX_FALSE_STARS + REQUIRED_STARS
        img_stars_n_brightest = img_stars.copy_n_brightest(beast.cvar.MAX_FALSE_STARS + beast.cvar.REQUIRED_STARS)
        img_const_n_brightest = beast.constellation_db(img_stars_n_brightest, beast.cvar.MAX_FALSE_STARS + 2, 1)
        lis = beast.db_match(self.C_DB, img_const_n_brightest)

        # Generate the match
        if lis.p_match > self.P_MATCH_THRESH and lis.winner.size() >= beast.cvar.REQUIRED_STARS:

            x = lis.winner.R11
            y = lis.winner.R21
            z = lis.winner.R31
            r = beast.cvar.MAXFOV / 2
            self.SQ_RESULTS.kdsearch(x, y, z, r, beast.cvar.THRESH_FACTOR * beast.cvar.IMAGE_VARIANCE)

            # Estimate density for constellation generation
            self.C_DB.results.kdsearch(x, y, z, r,beast.cvar.THRESH_FACTOR * beast.cvar.IMAGE_VARIANCE)
            fov_stars = self.SQ_RESULTS.from_kdresults()
            fov_db = beast.constellation_db(fov_stars, self.C_DB.results.r_size(), 1)
            self.C_DB.results.clear_kdresults()
            self.SQ_RESULTS.clear_kdresults()

            img_const = beast.constellation_db(img_stars, beast.cvar.MAX_FALSE_STARS + 2, 1)
            near = beast.db_match(fov_db, img_const)

            if near.p_match > self.P_MATCH_THRESH:
                match = near

        # Get solution -- for reference:
        #  - dec - rotation about the y-axis
        #  - ra  - rotation about the z-axis
        #  - ori - rotation about the camera axis
        if match is not None:
            match.winner.calc_ori()
            dec = match.winner.get_dec()
            ra = match.winner.get_ra()
            ori = match.winner.get_ori()
        else:
            dec, ra, ori = 0.0, 0.0, 0.0

        # Calculate how long it took to process
        runtime = time.time() - starttime

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.solve")

        # Return solution
        return dec, ra, ori, time

    # Camera control
    def modify(self, mod_string):
        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.modify")
            STACK_LAYERS = STACK_LAYERS + 1

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.modify")

        return 0

    # Error processing
    def error(self, err_string):
        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside StarTracker.error")
            STACK_LAYERS = STACK_LAYERS + 1

        # Handle what we can handle, everything else will be ignored
        if err_string == "image too blurry":
            self.modify("more sharp")
        elif err_string == "image contains too few stars":
            self.modify("increase gain")

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End StarTracker.error")

        # We always handle successfully
        return 0

# Server
class StarTrackerServer:

    # XML definition
    dbus = """
    <node>
        <interface name='org.OreSat.StarTracker'>
            <signal name='error'>
                <arg type='s' />
            </signal>
            <property name='coor' type='(dddd)' access='read'>
                <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true" />
            </property>
            <property name='filepath' type='s' access='read'>
                <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true" />
            </property>
        </interface>
    </node>
    """

    # Error signal
    error = signal()
    PropertiesChanged = signal()

    # Initialize properties and worker thread
    def __init__(self):

        # Properties
        self.dec = 0.0
        self.ra = 0.0
        self.ori = 0.0
        self.l_solve = 0.0
        self.t_solve = 0.0
        self.p_solve = ""
        self.interface_name = "org.OreSat.StarTracker"

        # Set up star tracker solver
        self.st = StarTracker()
        self.st_thread = threading.Thread(target = self.star_tracker)
        self.st_lock = threading.Lock()
        self.st_running = True

    # Star tracker thread
    def star_tracker(self):
        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside Server.star_tracker")
            STACK_LAYERS = STACK_LAYERS + 1

        # Keep going while we're running
        while (self.st_running):

            # Capture an image
            self.st_lock.acquire()
            self.p_solve, img = self.st.capture()
            # self.PropertiesChanged(self.interface_name, {"filepath": self.p_solve}, [])

            # Check the image
            check = self.st.preprocess(img)
            if check != "good":
                self.st.error(check)
                logger.warning(check + "(for {})".format(p_solve))
                error(check)
                time.sleep(0.5)
                continue

            # Solve the image
            self.dec, self.ra, self.ori, self.l_solve = self.st.solve(img)
            # self.PropertiesChanged(self.interface_name, {"coor": self.dec}, []) #TODO need to handle the struct
            if self.dec == self.ra == self.ori == 0.0:
                self.st.error("bad solve")
                logger.error("bad solve (for {})".format(p_solve))
                error("bad solve")
                time.sleep(0.5)
                continue

            # Update the solution timestamp
            self.t_solve = time.time()
            self.st_lock.release()

            # Send property signal
            self.PropertiesChanged(self.interface_name, {"filepath": self.p_solve}, [])
            time.sleep(0.5)

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End Server.star_tracker")

    # Start up solver and server
    def start(self, median_path, config_path, db_path, sample_dir = None):
        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside Server.start")
            STACK_LAYERS = STACK_LAYERS + 1

        # Start up star tracker
        self.st.startup(median_path, config_path, db_path, sample_dir = sample_dir)
        time.sleep(20)
        self.st_thread.start()
        logger.info("Started worker thread")

        # Start up D-Bus server
        bus = SystemBus()
        loop = GLib.MainLoop()
        bus.publish(self.interface_name, self)
        try:
            logger.info("Starting D-Bus loop...")
            loop.run()
        except KeyboardInterrupt as e:
            loop.quit()
            logger.info("Ended D-Bus loop")
            self.end()

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End Server.start")

    # Stop threads in preparation to exit
    def end(self):
        if(DEBUG_ENABLED):
            global STACK_LAYERS
            print(f"{STACK_LAYERS * ' '}Inside Server.end")
            STACK_LAYERS = STACK_LAYERS + 1

        self.st_running = False
        if self.st_thread.is_alive():
            self.st_thread.join()

        if(DEBUG_ENABLED):
            STACK_LAYERS = STACK_LAYERS - 1
            print(f"{STACK_LAYERS * ' '}End Server.end")

    # Coordinates
    @property
    def coor(self):
        self.st_lock.acquire()
        dec, ra, ori, t_solve = self.dec, self.ra, self.ori, self.t_solve
        self.st_lock.release()
        return (dec, ra, ori, t_solve)

    # Filepath of last solved image
    @property
    def filepath(self):
        self.st_lock.acquire()
        p_solve = self.p_solve
        self.st_lock.release()
        return p_solve

    # Return last solved file with coors (Reminder: Check if coords actually go with file)
    @property
    def last_solve(self):
        self.st_lock.acquire()
        p_solve = p_solve
        dec, ra, ori, t_solve = self.dec, self.ra, self.ori, self.t_solve
        self.st_lock.release()
        return (dec, ra, ori, t_solve, p_solve)


##########

# Test if run independently
if __name__ == "__main__":
    server = StarTrackerServer()
    db_root = "/usr/share/oresat-star-tracker/data/"
    data_root = db_root + "downsample/"
    server.start(data_root + "median_image.png", data_root + "calibration.txt", db_root + "hip_main.dat", sample_dir = data_root + "samples/")
