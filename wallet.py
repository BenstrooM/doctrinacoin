from ecdsa import SigningKey, VerifyingKey, SECP256k1

# algoritmus pro vytvareni penezenek a klicu 

class Wallet:
    def __init__(self):
        self.private_key = SigningKey.generate(curve=SECP256k1)
        self.public_key = self.private_key.get_verifying_key()

    def get_private_key(self):
        return self.private_key.to_string().hex()

    def get_public_key(self):
        return self.public_key.to_string().hex()

    def get_address(self): # adresa penezenky je v tomto pripade verejny klic (pro zachovani jednoduchosti)
        return self.get_public_key()

    def sign_transaction(self, sender, recipient, amount): # funkce pro podepisovani transakci pomoci ECDSA podpisu
        message = f"{sender}{recipient}{amount}".encode()
        signature = self.private_key.sign(message)
        return signature.hex()