import threading
import socket
from battleship import run_single_player_game_online, Board, parse_coordinate, TwoPlayerGame, SHIPS

#Turn to true for testing.
TEST_MODE = False


HOST = '127.0.0.1'
PORT = 5001

clients = []
clients_lock = threading.Lock()

waiting_clients = []
waiting_lock = threading.Lock()

def handle_incoming_client(conn, addr):
    try:
        rfile = conn.makefile('r')
        wfile = conn.makefile('w')
        print(f"[INFO] Client joined: {addr}")
        lobby_loop(rfile, wfile, conn)
    except Exception as e:
        print(f"[ERROR] Client setup failed: {e}")
        try: conn.close()
        except: pass

def start_match_if_possible():
    with waiting_lock:
        if len(waiting_clients) >= 2:
            client1 = waiting_clients.pop(0)
            client2 = waiting_clients.pop(0)

            rfile1, wfile1, conn1 = client1
            rfile2, wfile2, conn2 = client2

            print("[INFO] Starting a new game")

            def game_and_return_to_lobby():
                run_two_player_game_online(rfile1, wfile1, rfile2, wfile2)
                lobby_loop(rfile1, wfile1, conn1)
                lobby_loop(rfile2, wfile2, conn2)

            threading.Thread(target=game_and_return_to_lobby, daemon=True).start()



def run_two_player_game_online(rfile1, wfile1, rfile2, wfile2):
    
    test_ships = [("TestShip", 1)] if TEST_MODE else SHIPS
    

    game = TwoPlayerGame()
    rfiles = [rfile1, rfile2]
    wfiles = [wfile1, wfile2]

    def send(wfile, msg):
        wfile.write(msg + '\n')
        wfile.flush()

    def send_board(wfile, board_grid):
        wfile.write("GRID\n")
        wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(10)) + '\n')
        for r in range(10):
            row_label = chr(ord('A') + r)
            row_str = " ".join(board_grid[r][c] for c in range(10))
            wfile.write(f"{row_label:2} {row_str}\n")
        wfile.write('\n')
        wfile.flush()
        
    def send_player_board(wfile, board):
        wfile.write("Your current board:\n")
        wfile.write("GRID\n")
        wfile.write("  " + " ".join(str(i + 1).rjust(2) for i in range(board.size)) + '\n')
        for r in range(board.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(board.hidden_grid[r][c] for c in range(board.size))
            wfile.write(f"{row_label:2} {row_str}\n")
        wfile.write('\n')
        wfile.flush()
    

    # Step 1: Manual ship placement (parallel threads)
    def prompt_placement(player_index):
        w = wfiles[player_index]
        r = rfiles[player_index]

        send(w, f"Welcome Player {player_index + 1}! Let's place your ships.")
        board = game.player_boards[player_index]
        
        send(w, "Your board is empty. Here's what it looks like now:")
        send_player_board(w, board)

        for ship_name, ship_size in test_ships:
            while True:
                try:
                    send(w, f"Place your {ship_name} (size {ship_size})")
                    send(w, "Enter starting coordinate (e.g. A1):")
                    coord = r.readline().strip()

                    send(w, "Enter orientation (H for horizontal, V for vertical):")
                    orient = r.readline().strip().upper()

                    # Validate and place immediately
                    row, col = parse_coordinate(coord)
                    if orient == 'H':
                        orientation = 0
                    elif orient == 'V':
                        orientation = 1
                    else:
                        send(w, "Invalid orientation. Please enter H or V.")
                        continue

                    if not board.can_place_ship(row, col, ship_size, orientation):
                        send(w, f"Cannot place {ship_name} at {coord} with orientation {orient}. Try again.")
                        continue

                    occupied = board.do_place_ship(row, col, ship_size, orientation)
                    board.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied
                    })
                    send(w, f"{ship_name} placed successfully.")
                    send_player_board(w, board)
                    break  # Ship placed successfully

                except Exception as e:
                    send(w, f"Error: {e}. Try again.")

        game.ships_placed[player_index] = True
        send(w, "All ships placed successfully. Waiting for opponent...\n")


    # Launch placement in parallel threads
    threads = []
    for i in [0, 1]:
        t = threading.Thread(target=prompt_placement, args=(i,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    if not all(game.ships_placed):
        # One player failed placement; end session
        for w in wfiles:
            send(w, "Game could not start due to ship placement error.")
        return

    # Step 2: Start game
    for w in wfiles:
        send(w, "Both players ready! Game begins.")

    # Turn loop
    print("[DEBUG] Entering game loop... active =", game.active)
    while game.active:
        try:
            current = game.get_current_player_index()
            opponent = game.get_opponent_index()
            r = rfiles[current]
            w = wfiles[current]
            opp_w = wfiles[opponent]

            # Show opponent board
            send_board(w, game.get_visible_board_for_player(current))
            send(w, "Your turn! Enter coordinate to fire at (or 'quit'):")

            move = r.readline()
            if not move:
                send(w, "Disconnected.")
                send(opp_w, "Opponent disconnected. You win!")
                break

            move = move.strip()
            if move.lower() == 'quit':
                send(w, "You quit. Goodbye!")
                send(opp_w, "Opponent quit. You win!")
                break

            result, sunk, game_over, message = game.fire(move)

            opponent_message = message.replace(" You win!", "")

            send(w, message)  # Full message to current player
            send(opp_w, f"Opponent fired at {move}: {opponent_message}")  # Cleaned message

            if game_over:
                send(w, "You win!")
                send(opp_w, "You lose!")
                break
        except Exception as e:
            print("[ERROR] Exception in game loop:", e)

    # Clean up (optional)
    for w in wfiles:
        try:
            w.write("Game over. Returning to the lobby...\n")
            w.flush()
        except:
            pass
    

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
        s.listen()

        while True:
            conn, addr = s.accept()
            print(f"[INFO] New client from {addr}")
            threading.Thread(target=handle_incoming_client, args=(conn, addr), daemon=True).start()

def lobby_loop(rfile, wfile, conn):
    try:
        while True:
            wfile.write("Waiting for another player...\n")
            wfile.flush()

            with waiting_lock:
                waiting_clients.append((rfile, wfile, conn))

            while True:
                with waiting_lock:
                    if (rfile, wfile, conn) not in waiting_clients:
                        break  # matched into a game
                time.sleep(0.5)  # wait to be matched

    except Exception as e:
        print(f"[INFO] Client disconnected during lobby wait: {e}")
        try: conn.close()
        except: pass

if __name__ == "__main__":
    main()