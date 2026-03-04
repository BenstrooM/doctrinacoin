# program zaroven slouzi k uceni, proto je plny komentaru

import hashlib
import json
import time
import os
import ssl
import certifi
import threading
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError

# bloky


class Block:
    # spusti se pokazde, kdyz se vytvori novy block
    def __init__(self, index, transactions, previous_hash, nonce=0):
        self.index = index
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.timestamp = time.time()
        self.hash = self.calculate_hash()

    def calculate_hash(self):  # prevede data bloku do JSON formatu a zahashuje pomoci sha256
        block_string = json.dumps({
            "index": self.index,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "timestamp": self.timestamp
        }, sort_keys=True)  # zajistuje spravnost poradi klicu
        return hashlib.sha256(block_string.encode()).hexdigest()

# samotny blockchain


class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.difficulty = 5
        self.base_mining_reward = 50  # pocatecni odmena za vytezeni bloku
        self.halving_interval = 10  # odmena se snizi na polovinu kazdych 10 bloku
        self.min_reward = 0.001  # minimalni odmena za vytezeni bloku
        self.target_block_time = 60  # cilovy cas na vytezeni bloku v sekundach
        self.adjustment_interval = 5  # po kolika blocich se upravi obtiznost
        self.mining_generation = 0
        self.chain_lock = threading.Lock()
        if not self.load_chain():
            self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, [], "0")
        genesis_block.hash = genesis_block.calculate_hash()
        self.chain.append(genesis_block)

    def _get_mongo_client(self):
        mongo_uri = os.environ.get("MONGO_URI")
        if not mongo_uri:
            return None
        from pymongo import MongoClient
        return MongoClient(mongo_uri, tls=True, tlsCAFile=certifi.where(),
                           serverSelectionTimeoutMS=5000)

    def get_last_block(self):
        return self.chain[-1]  # posledni blok v retezci

    def get_mining_reward(self):  # vypocet odmeny za tezeni s halvingem
        block_height = len(self.chain)
        halvings = block_height // self.halving_interval  # kolikrat uz doslo k halvingu
        # odmena se snizi na polovinu s kazdym halvingem
        reward = self.base_mining_reward / (2 ** halvings)
        # odmena nesmi klesnout pod minimum
        return max(reward, self.min_reward)

    def adjust_difficulty(self):  # automaticka uprava obtiznosti tezeni
        if len(self.chain) < self.adjustment_interval + 1:
            return  # nedostatek bloku pro upravu

        if len(self.chain) % self.adjustment_interval != 0:
            return  # jeste neni cas na upravu

        # porovnani skutecneho casu s ocekavanym
        last_block = self.chain[-1]
        first_block = self.chain[-self.adjustment_interval]
        actual_time = last_block.timestamp - first_block.timestamp
        expected_time = self.target_block_time * self.adjustment_interval

        if actual_time < expected_time / 2:
            self.difficulty += 1  # bloky jsou prilis rychle, zvysit obtiznost
        elif actual_time > expected_time * 2:
            self.difficulty -= 1  # bloky jsou prilis pomale, snizit obtiznost

        # obtiznost musi zustat v rozumnem rozmezi
        self.difficulty = max(1, min(8, self.difficulty))
        print(
            f"Difficulty adjusted to {self.difficulty} (actual: {actual_time:.0f}s, expected: {expected_time:.0f}s)")

    # funkce pro tezeni bloku
    def mine_pending_transactions(self, miner_address, progress=None):
        generation = self.mining_generation

        # vypocet celkovych poplatku z transakci
        total_fees = 0
        for tx in self.pending_transactions:
            total_fees += tx.get("fee", 0)

        reward_transaction = {  # odmena pro minera (odmena za blok + poplatky)
            "sender": "NETWORK",
            "recipient": miner_address,
            "amount": round(self.get_mining_reward() + total_fees, 8)
        }
        transactions = self.pending_transactions.copy()
        transactions.append(reward_transaction)

        new_block = Block(  # vytvoreni noveho bloku (do ktereho se pridaji transakce z mempoolu)
            index=len(self.chain),
            transactions=transactions,
            previous_hash=self.get_last_block().hash
        )

        # proof of work v novem bloku
        new_block = self.proof_of_work(new_block, generation, progress)

        if new_block is None:
            return False

        with self.chain_lock:
            if self.mining_generation != generation:
                return False
            self.chain.append(new_block)
            self.pending_transactions = []
            self.mining_generation += 1
            self.save_chain()
            self.adjust_difficulty()
            return True

    def proof_of_work(self, block, generation, progress=None):
        block.nonce = 0
        computed_hash = block.calculate_hash()
        start_time = time.time()

        while not computed_hash.startswith("0" * self.difficulty):
            if self.mining_generation != generation:
                if progress:
                    progress["current_nonce"] = 0
                    progress["current_hash"] = ""
                    progress["hashes_per_second"] = 0
                return None

            block.nonce += 1
            computed_hash = block.calculate_hash()

            if progress:
                progress["current_nonce"] = block.nonce
                progress["current_hash"] = computed_hash
                elapsed = time.time() - start_time
                if elapsed > 0:
                    progress["hashes_per_second"] = int(block.nonce / elapsed)

        block.hash = computed_hash
        if progress:
            progress["current_nonce"] = 0
            progress["current_hash"] = ""
            progress["hashes_per_second"] = 0
        return block

    def add_transaction(self, sender, recipient, amount, signature, public_key_hex, fee=0):
        if not self.verify_transaction(sender, recipient, amount, signature, public_key_hex):
            raise Exception("Invalid transaction signature!")

        if amount <= 0:
            raise Exception("Transaction amount must be greater than zero")

        if fee < 0:
            raise Exception("Fee cannot be negative")

        if sender != "NETWORK":
            balance = self.get_balance(sender)
            total_cost = amount + fee  # celkova cena = castka + poplatek
            if balance < total_cost:
                raise Exception(
                    f"Insufficient funds! Available balance: {balance} DCT, needed: {total_cost} DCT")

        transaction = {
            "sender": sender,
            "recipient": recipient,
            "amount": amount,
            "fee": fee
        }
        self.pending_transactions.append(transaction)

    # overeni transakce pomoci ECDSA podpisu
    def verify_transaction(self, sender, recipient, amount, signature, public_key_hex):
        try:
            public_key = VerifyingKey.from_string(
                bytes.fromhex(public_key_hex),
                curve=SECP256k1
            )
            message = f"{sender}{recipient}{amount}".encode()
            return public_key.verify(bytes.fromhex(signature), message)
        except BadSignatureError:
            return False

    def get_balance(self, address):  # funkce pro checkovani zustatku na adrese
        balance = 0
        for block in self.chain:
            for transaction in block.transactions:
                if transaction["sender"] == address:
                    balance -= transaction["amount"]
                    # odecist poplatek z zustatku odesilatele
                    balance -= transaction.get("fee", 0)
                if transaction["recipient"] == address:
                    balance += transaction["amount"]
        return balance

    def is_chain_valid(self):  # kontrola integrity blockchainu
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.hash != current.calculate_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True

    def save_chain(self):
        client = self._get_mongo_client()
        if client:
            try:
                db = client["doctrinacoin"]
                collection = db["chain"]
                chain_data = []
                for block in self.chain:
                    chain_data.append({
                        "index": block.index,
                        "transactions": block.transactions,
                        "previous_hash": block.previous_hash,
                        "nonce": block.nonce,
                        "timestamp": block.timestamp,
                        "hash": block.hash
                    })
                collection.delete_many({})
                collection.insert_many(chain_data)
                client.close()
            except Exception as e:
                print(f"MongoDB save failed: {e}")
        else:
            chain_data = []
            for block in self.chain:
                chain_data.append({
                    "index": block.index,
                    "transactions": block.transactions,
                    "previous_hash": block.previous_hash,
                    "nonce": block.nonce,
                    "timestamp": block.timestamp,
                    "hash": block.hash
                })
            with open("chain.json", "w") as f:
                json.dump(chain_data, f)

    def load_chain(self):
        client = self._get_mongo_client()
        if client:
            try:
                db = client["doctrinacoin"]
                collection = db["chain"]
                chain_data = list(collection.find(
                    {}, {"_id": 0}).sort("index", 1))
                client.close()
                if not chain_data:
                    return False
                self.chain = []
                for block_data in chain_data:
                    block = Block.__new__(Block)
                    block.index = block_data["index"]
                    block.transactions = block_data["transactions"]
                    block.previous_hash = block_data["previous_hash"]
                    block.nonce = block_data["nonce"]
                    block.timestamp = block_data["timestamp"]
                    block.hash = block_data["hash"]
                    self.chain.append(block)
                return True
            except Exception as e:
                print(f"MongoDB load failed: {e}")
                return False
        else:
            try:
                with open("chain.json", "r") as f:
                    chain_data = json.load(f)
                self.chain = []
                for block_data in chain_data:
                    block = Block.__new__(Block)
                    block.index = block_data["index"]
                    block.transactions = block_data["transactions"]
                    block.previous_hash = block_data["previous_hash"]
                    block.nonce = block_data["nonce"]
                    block.timestamp = block_data["timestamp"]
                    block.hash = block_data["hash"]
                    self.chain.append(block)
                return True
            except FileNotFoundError:
                return False
