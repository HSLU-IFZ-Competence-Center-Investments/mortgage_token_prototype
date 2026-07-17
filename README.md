# How to run demo

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

4. Mint test stablecoins to any accounts that need them to execute functions. This is done in the sidebar.



# Disclamer

Any concepts, models, data, software elements, or recommendations included are provided solely for research, demonstration, or illustrative purposes. They are not intended for production use, system integration, or operational implementation and do not constitute any representation regarding regulatory compliance. Any use in operational or regulatory-relevant contexts is outside the scope of responsibility of the IFZ, HSLU.