DEMO:
1. anvil                         # start local chain in one terminal
2. forge script script/MortgageToken.s.sol --rpc-url http://127.0.0.1:8545 --private-key <anvil-printed-key> --broadcast
   # note the deployed contract address printed in the logs
3. streamlit run frontend/app.py
   # in the sidebar: paste the RPC url, contract address, and the owner private key used to deploy