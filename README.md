# How to run demo

## Local (Anvil)

1. Start local chain in one terminal:
   ```
   anvil
   ```

2. Deploy the contract:
   ```
   forge script script/MortgageToken.s.sol --rpc-url http://127.0.0.1:8545 --private-key <YOUR_PRIVATE_KEY> --broadcast
   ```
   Note the deployed contract address printed in the logs.

3. Run the app:
   ```
   streamlit run app.py
   ```
   In the sidebar: paste the RPC url, contract address, and the owner private key used to deploy.

4. Mint test stablecoins to any accounts that need them to execute functions, using `cast send` (works
   against `MockStablecoin`, which has an open `mint()`):
   ```
   cast send <MOCK_STABLECOIN_ADDRESS> "mint(address,uint256)" <RECIPIENT_ADDRESS> <AMOUNT_IN_UNITS> \
     --rpc-url http://127.0.0.1:8545 --private-key <ANY_PRIVATE_KEY>
   ```

## Testnet (e.g. Sepolia)

### Prerequisites

Before starting the app, set up two separate MetaMask accounts — one for the **issuer** and one for the
**investor** (using two different accounts, rather than one, is what lets the investor approval flow
below actually reflect the real separation of custody). Both accounts need to be topped up with:

- **Sepolia test ETH** (for gas) — faucet: https://cloud.google.com/application/web3/faucet/ethereum/sepolia
- **Sepolia test USDC** — faucet: https://faucet.circle.com

1. Deploy the contract:
   ```
   forge script script/MortgageToken.s.sol --rpc-url https://ethereum-sepolia-rpc.publicnode.com --private-key <YOUR_PRIVATE_KEY> --broadcast
   ```
   Note the deployed `MortgageToken` address printed in the logs. `

   Take the private key of a Issuer account.

   Sepolia RPC URL: https://ethereum-sepolia-rpc.publicnode.com

   USDC testnet contract: 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238

2. Run the app and point the sidebar at `<SEPOLIA_RPC_URL>` and the deployed contract address.


## Investor approval via MetaMask (Transfer to Investor step)

The investor must approve the `MortgageToken` contract to pull the purchase price from their own wallet
before the issuer can settle the transfer. A real investor won't hand their private key to the app, so
this step is done from the investor's own MetaMask, outside the app.

1. In the app's **Transfer to Investor** tab, enter the mortgage ID, purchase price, and investor address.
   If the investor hasn't approved enough yet, the tab shows a warning box with the exact `spender` and
   `amount` values and the raw hex calldata for `approve()`.
2. In MetaMask: **Settings → Advanced → enable "Show Hex Data"** (adds a hex data field to the Send screen).
3. Switch to the **investor's account**, on the same network as the deployment (e.g. Sepolia).
4. Go to **Send** and fill in:
   - **Recipient**: the **stablecoin contract address** (e.g. `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`
     for Sepolia testnet USDC) — **not** the `MortgageToken` contract address. 
   - **Amount**: `0` (this transaction moves no ETH — the USDC amount is encoded in the hex data instead)
   - **Hex Data**: the calldata shown in the app's warning box
5. Confirm and sign from the investor's wallet.
6. Once mined, go back to the app and click **"Settle Purchase and Transfer"** — this step is signed by
   the issuer's own private key from the sidebar (no MetaMask needed here; a real bank would hold this key
   in its own backend, not click through a wallet UI by hand).


# Disclamer

Any concepts, models, data, software elements, or recommendations included are provided solely for research, demonstration, or illustrative purposes. They are not intended for production use, system integration, or operational implementation and do not constitute any representation regarding regulatory compliance. Any use in operational or regulatory-relevant contexts is outside the scope of responsibility of the IFZ, HSLU.