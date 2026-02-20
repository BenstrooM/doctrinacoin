# program zaroven slouzi k uceni, proto je plny komentaru

import hashlib 
import json # prevadeni python objektu do json formatu (stringů)
import time 
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError 

# bloky

class Block:   
    def __init__(self, index, transactions, previous_hash, nonce=0): # spusti se pokazde, kdyz se vytvori novy block
        self.index = index 
        self.transactions = transactions 
        self.previous_hash = previous_hash  
        self.nonce = nonce
        self.timestamp = time.time()
        self.hash = self.calculate_hash()

    def calculate_hash(self): # prevede data bloku do JSON formatu a zahashuje pomoci sha256
        block_string = json.dumps({
            "index": self.index,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "timestamp": self.timestamp
        }, sort_keys=True) # zajistuje spravnost poradi klicu
        return hashlib.sha256(block_string.encode()).hexdigest()
    
# samotny blockchain

class Blockchain:
    def __init__(self):
        self.chain = [] # seznam bloku
        self.pending_transactions = [] #mempool
        self.difficulty = 5
        self.mining_reward = 50
        self.current_nonce = 0
        self.current_hash_attempt = ""
        self.hashes_per_second = 0
        self.create_genesis_block()
    
    def create_genesis_block(self):
        genesis_block = Block(0, [], "0")
        genesis_block.hash = genesis_block.calculate_hash()
        self.chain.append(genesis_block)
    
    def get_last_block(self):
        return self.chain[-1] #posledni blok v retezci
    
    def mine_pending_transactions(self, miner_address): # funkce pro tezeni bloku
        reward_transaction = { # odmena pro minera 
            "sender": "NETWORK",
            "recipient": miner_address,
            "amount": self.mining_reward
        }
        self.pending_transactions.append(reward_transaction)

        new_block = Block( # vytvoreni noveho bloku (do ktereho se pridaji transakce z mempoolu)
            index=len(self.chain),
            transactions=self.pending_transactions,
            previous_hash=self.get_last_block().hash
        )

        new_block = self.proof_of_work(new_block) # proof of work v novem bloku
        self.chain.append(new_block)
        self.pending_transactions = []

    def proof_of_work(self, block):
        block.nonce = 0
        computed_hash = block.calculate_hash()
        start_time = time.time()

        while not computed_hash.startswith("0" * self.difficulty):
            block.nonce += 1
            computed_hash = block.calculate_hash()
            self.current_nonce = block.nonce
            self.current_hash_attempt = computed_hash

            elapsed = time.time() - start_time
            if elapsed > 0:
                self.hashes_per_second = block.nonce / elapsed

        block.hash = computed_hash
        self.current_nonce = 0
        self.current_hash_attempt = ""
        self.hashes_per_second = 0
        return block
    
    def add_transaction(self, sender, recipient, amount, signature, public_key_hex):
        if not self.verify_transaction(sender, recipient, amount, signature, public_key_hex):
            raise Exception("Invalid transaction signature!")

        if amount <= 0:
            raise Exception("Transaction amount must be greater than zero")

        balance = self.get_balance(sender)
        if sender != "NETWORK":
            balance = self.get_balance(sender)
            if balance < amount:
                raise Exception(f"Insufficient funds! Available balance: {balance} DCT")
        
        transaction = {
            "sender": sender,
            "recipient": recipient,
            "amount": amount
        }
        self.pending_transactions.append(transaction)
    
    def verify_transaction(self, sender, recipient, amount, signature, public_key_hex): # overeni transakce pomoci ECDSA podpisu
        try:
            public_key = VerifyingKey.from_string(
                bytes.fromhex(public_key_hex), 
                curve=SECP256k1
            )
            message = f"{sender}{recipient}{amount}".encode()
            return public_key.verify(bytes.fromhex(signature), message)
        except BadSignatureError:
            return False
        
    def get_balance(self, address): # funkce pro checkovani zustatku na adrese
        balance = 0
        for block in self.chain:
            for transaction in block.transactions:
                if transaction["sender"] == address:
                    balance -= transaction["amount"]
                if transaction["recipient"] == address:
                    balance += transaction["amount"]
        return balance

    def is_chain_valid(self): # kontrola integrity blockchainu
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.hash != current.calculate_hash():
                return False
            if current.previous_hash != previous.hash:
                return False

        return True





