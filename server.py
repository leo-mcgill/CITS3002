import threading
import socket
from battleship import run_single_player_game_online

HOST = '127.0.0.1'
PORT = 5001

clients = []
clients_lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[INFO] Client connected from {addr}")
    with conn:
        rfile = conn.makefile('r')
        wfile = conn.makefile('w')

        # Wait for the game to start (after both clients connect)
        wfile.write("Waiting for another player to join...\n")
        wfile.flush()

        # Block until we have both players
        while True:
            with clients_lock:
                if len(clients) == 2:
                    break

        # Inform the client that the game is starting
        wfile.write("Game starting! You are now playing.\n")
        wfile.flush()

        try:
            run_single_player_game_online(rfile, wfile)
        except Exception as e:
            print(f"[ERROR] Exception while handling client {addr}: {e}")

    print(f"[INFO] Client {addr} disconnected.")
    

def main():
    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(2)

        while len(clients) < 2:
            conn, addr = s.accept()
            with clients_lock:
                if len(clients) < 2:
                    clients.append((conn, addr))
                    threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
                else:
                    # Reject extra connections
                    conn.sendall(b"Server already has two players. Try again later.\n")
                    conn.close()

if __name__ == "__main__":
    main()