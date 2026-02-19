from flask import Flask, request, jsonify, render_template # webovy framework pro vytvareni APIs
from blockchain import Blockchain
from wallet import Wallet
import threading

app = Flask(__name__)
blockchain = Blockchain()

mining_status = {
    "is_mining": False,
    "message": "",
    "block_index": None,
    "hash": None,
    "transactions": None
}

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

    try:
        blockchain.add_transaction(
            data["sender"],
            data["recipient"],
            data["amount"],
            data["signature"],
            data["public_key"]
        )
        return jsonify({"message": "Transaction added to pending pool"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    
@app.route("/mine", methods=["POST"])
def mine():
    global mining_status

    if mining_status["is_mining"]:
        return jsonify({"error": "Already mining a block!"}), 400

    data = request.get_json()

    if "miner_address" not in data:
        return jsonify({"error": "Missing miner address"}), 400

    def mining_thread():
        global mining_status
        mining_status["is_mining"] = True
        mining_status["message"] = "Mining in progress..."
        mining_status["hash"] = None
        mining_status["block_index"] = None
        mining_status["transactions"] = None

        blockchain.mine_pending_transactions(data["miner_address"])
        last_block = blockchain.get_last_block()

        mining_status["is_mining"] = False
        mining_status["message"] = "Block mined successfully!"
        mining_status["block_index"] = last_block.index
        mining_status["hash"] = last_block.hash
        mining_status["transactions"] = last_block.transactions

    thread = threading.Thread(target=mining_thread)
    thread.start()

    return jsonify({"message": "Mining started!"})

@app.route("/mine/status", methods=["GET"])
def mine_status():
    return jsonify(mining_status)

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

        return jsonify({
            "is_mining": mining_status["is_mining"],
            "current_nonce": nonce,
            "current_hash": blockchain.current_hash_attempt,
            "hashes_per_second": int(hps),
            "estimated_remaining": estimate
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "is_mining": mining_status["is_mining"],
            "current_nonce": blockchain.current_nonce,
            "current_hash": blockchain.current_hash_attempt,
            "hashes_per_second": 0,
            "estimated_remaining": "Calculating..."
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)