from flask import Flask, request, jsonify, render_template # webovy framework pro vytvareni APIs
from blockchain import Blockchain
from wallet import Wallet
import threading
import os
port = int(os.environ.get("PORT", 5000))

app = Flask(__name__)
blockchain = Blockchain()

# per-miner status tracking: address -> {status, block_index, hash, transactions}
active_miners = {}

@app.route("/wallet/new", methods=["GET"]) # vytvoreni nove penezenky
def new_wallet():
    wallet = Wallet()
    return jsonify({
        "private_key": wallet.get_private_key(), # v realnem pripade by se soukormy klic nemel posilat pres sit
        "public_key": wallet.get_public_key(),
        "address": wallet.get_address()
    })

@app.route("/balance/<address>", methods=["GET"]) # ziskani zustatku na dane adrese
def get_balance(address):
    balance = blockchain.get_balance(address)
    return jsonify({
        "address": address,
        "balance": balance
    })

@app.route("/transaction/new", methods=["POST"]) # posilani nove transakce
def new_transaction():
    data = request.get_json()
    required_fields = ["sender", "recipient", "amount", "signature", "public_key"]
    
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing fields"}), 400

    fee = data.get("fee", 0) # poplatek je volitelny, vychozi hodnota 0

    try:
        blockchain.add_transaction(
            data["sender"],
            data["recipient"],
            data["amount"],
            data["signature"],
            data["public_key"],
            fee=fee
        )
        return jsonify({"message": "Transaction added to pending pool"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
@app.route("/mine", methods=["POST"])
def mine():
    data = request.get_json()

    if "miner_address" not in data:
        return jsonify({"error": "Missing miner address"}), 400

    address = data["miner_address"]

    # prevent same address from mining twice at once
    if address in active_miners and active_miners[address]["status"] == "mining":
        return jsonify({"error": "You are already mining!"}), 400

    def run_mining(miner_address):
        result = blockchain.mine_pending_transactions(miner_address)
        
        if result:
            last_block = blockchain.get_last_block()
            active_miners[miner_address] = {
                "status": "won",
                "block_index": last_block.index,
                "hash": last_block.hash,
                "transactions": last_block.transactions
            }
        else:
            active_miners[miner_address] = {
                "status": "lost",
                "block_index": None,
                "hash": None,
                "transactions": None
            }

    # set status before starting thread to avoid race condition
    active_miners[address] = {
        "status": "mining",
        "block_index": None,
        "hash": None,
        "transactions": None
    }

    thread = threading.Thread(target=run_mining, args=(address,))
    thread.start()

    return jsonify({"message": "Mining started!"})

@app.route("/mine/status", methods=["GET"])
def mine_status():
    address = request.args.get("address")
    if not address or address not in active_miners:
        return jsonify({"status": "idle"})
    return jsonify(active_miners[address])

@app.route("/mine/progress", methods=["GET"])
def mine_progress():
    try:
        hps = blockchain.hashes_per_second
        nonce = blockchain.current_nonce
        expected_attempts = 16 ** blockchain.difficulty
        
        if hps > 0:
            remaining_attempts = max(0, expected_attempts - nonce)
            estimated_seconds = remaining_attempts / hps
            minutes = int(estimated_seconds // 60)
            seconds = int(estimated_seconds % 60)
            estimate = f"{minutes}m {seconds}s remaining"
        else:
            estimate = "Calculating..."

        # count how many miners are currently active
        mining_count = sum(1 for m in active_miners.values() if m["status"] == "mining")

        return jsonify({
            "is_mining": mining_count > 0,
            "active_miners": mining_count,
            "current_nonce": nonce,
            "current_hash": blockchain.current_hash_attempt,
            "hashes_per_second": int(hps),
            "estimated_remaining": estimate
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "is_mining": False,
            "active_miners": 0,
            "current_nonce": blockchain.current_nonce,
            "current_hash": blockchain.current_hash_attempt,
            "hashes_per_second": 0,
            "estimated_remaining": "Calculating..."
        })

@app.route("/reward", methods=["GET"]) # aktualni odmena za tezeni
def get_reward():
    reward = blockchain.get_mining_reward()
    block_height = len(blockchain.chain)
    next_halving = blockchain.halving_interval - (block_height % blockchain.halving_interval)
    return jsonify({
        "current_reward": reward,
        "block_height": block_height,
        "next_halving_in": next_halving,
        "halving_interval": blockchain.halving_interval
    })
    
@app.route("/chain", methods=["GET"]) # ziskani celeho blockchainu
def get_chain():
    chain_data = []
    for block in blockchain.chain:
        chain_data.append({
            "index": block.index,
            "timestamp": block.timestamp,
            "transactions": block.transactions,
            "hash": block.hash,
            "previous_hash": block.previous_hash,
            "nonce": block.nonce
        })
    return jsonify({
        "chain": chain_data,
        "length": len(blockchain.chain)
    })

@app.route("/validate", methods=["GET"]) # validace blockchainu
def validate():
    is_valid = blockchain.is_chain_valid()
    return jsonify({"is_valid": is_valid})

@app.route("/sign", methods=["POST"])
def sign():
    data = request.get_json()
    from ecdsa import SigningKey, SECP256k1
    private_key = SigningKey.from_string(
        bytes.fromhex(data["private_key"]),
        curve=SECP256k1
    )
    message = f"{data['sender']}{data['recipient']}{data['amount']}".encode()
    signature = private_key.sign(message)
    return jsonify({"signature": signature.hex()})

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/test")
def test():
    return jsonify({"hashes_per_second": blockchain.hashes_per_second})

@app.route("/test-save")
def test_save():
    try:
        blockchain.save_chain()
        return jsonify({"message": "saved successfully"})
    except Exception as e:
        return jsonify({"error": str(e)})
    
@app.route("/reset", methods=["POST"])
def reset_chain():
    data = request.get_json()
    if data.get("confirm") != "RESET":
        return jsonify({"error": "Send confirm: RESET to proceed"}), 400
    blockchain.chain = []
    blockchain.pending_transactions = []
    blockchain.mining_generation += 1
    blockchain.create_genesis_block()
    blockchain.save_chain()
    return jsonify({"message": "Blockchain reset to genesis block"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)