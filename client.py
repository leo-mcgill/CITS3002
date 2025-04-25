import threading
import socket

HOST = '127.0.0.1'
PORT = 5001

running = True


def receive_messages(rfile):
     while running:
        try:
            line = rfile.readline()
            if not line:
                print("[INFO] Server disconnected.")
                break
            line = line.strip()
            if line == "GRID":
                print("\n[Board]")
                while True:
                    board_line = rfile.readline()
                    if not board_line or board_line.strip() == "":
                        break
                    print(board_line.strip())
            else:
                print(line)
        except Exception as e:
            print(f"[ERROR] Receiving thread: {e}")
            break

def main():
    global running
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        rfile = s.makefile('r')
        wfile = s.makefile('w')

        # Start the receiving thread
        receiver = threading.Thread(
            target=receive_messages, 
            args=(rfile,), daemon=True
        )
        receiver.start()

        try:
            while running:
                user_input = input(">> ")
                if user_input.lower() == "quit":
                    running = False
                    break
                wfile.write(user_input + '\n')
                wfile.flush()
        except KeyboardInterrupt:
            print("\n[INFO] Client exiting...")
        finally:
            running = False
            s.close()

if __name__ == "__main__":
    main()