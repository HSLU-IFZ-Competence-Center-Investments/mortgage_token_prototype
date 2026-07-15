import json
import time
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = ROOT / "out" / "MortgageToken.sol" / "MortgageToken.json"
STATE_PATH = Path(__file__).resolve().parent / ".frontend_state.json"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

st.set_page_config(page_title="Mortgage Token Demo", page_icon="\U0001F3E0", layout="centered")


def clean_hex_input(value: str) -> str:
    """Strip whitespace and stray quote characters from a pasted hex string
    (private key or address), which are commonly copied in by accident."""
    return value.strip().strip("'\"").strip()


def load_abi() -> list:
    if not ARTIFACT_PATH.exists():
        st.error(
            f"Build artifact not found at {ARTIFACT_PATH}.\n\n"
            "Run `forge build` in the project root first."
        )
        st.stop()
    with open(ARTIFACT_PATH) as f:
        return json.load(f)["abi"]


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(**kwargs) -> None:
    state = load_state()
    state.update(kwargs)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


saved_state = load_state()

st.title("\U0001F3E0 Mortgage Token Demo")
st.caption("Prototype frontend for the MortgageToken ERC-721 contract, running against a local Anvil node.")

with st.sidebar:
    st.header("Connection")
    rpc_url = st.text_input("RPC URL", value=saved_state.get("rpc_url", "http://127.0.0.1:8545"))
    contract_address = st.text_input("Contract address", value=saved_state.get("contract_address", ""))
    owner_private_key = clean_hex_input(
        st.text_input(
            "Owner private key",
            type="password",
            help="Private key of the contract owner (needed to sign createMortgage transactions).",
        )
    )
    save_state(rpc_url=rpc_url, contract_address=contract_address)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    connected = w3.is_connected()
    st.markdown(f"**Node status:** {'\U0001F7E2 connected' if connected else '\U0001F534 not connected'}")

    contract = None
    if connected and contract_address:
        try:
            abi = load_abi()
            contract = w3.eth.contract(address=Web3.to_checksum_address(clean_hex_input(contract_address)), abi=abi)
            owner = contract.functions.owner().call()
            st.markdown(f"**Contract owner:** `{owner}`")
        except Exception as e:
            st.error(f"Could not load contract: {e}")

tab_create, tab_lookup = st.tabs(["Create Mortgage", "Look Up Mortgage"])

with tab_create:
    st.subheader("Create a new mortgage token")

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    with st.form("create_mortgage_form"):
        col1, col2 = st.columns(2)
        with col1:
            borrower = st.text_input("Borrower address")
        with col2:
            investor = st.text_input("Investor address")

        col3, col4 = st.columns(2)
        with col3:
            principal_amount = st.number_input("Principal amount", min_value=0.0, value=500000.0, step=1000.0)
        with col4:
            currency = st.text_input("Currency", value="CHF")

        col5, col6 = st.columns(2)
        with col5:
            maturity = st.date_input("Maturity date", value=date(date.today().year + 1, date.today().month, date.today().day))
        with col6:
            interest_rate_pct = st.number_input("Interest rate (%)", min_value=0.0, value=2.5, step=0.1)

        payment_mode = st.selectbox("Payment mode", ["SIC", "Stablecoin"])
        stablecoin_address = ""
        if payment_mode == "Stablecoin":
            stablecoin_address = st.text_input("Stablecoin address")

        col7, col8 = st.columns(2)
        with col7:
            loan_agreement_id = st.text_input("Loan agreement ID")
        with col8:
            land_registry_extract_id = st.text_input("Land registry extract ID")

        document_text = st.text_area(
            "Document references (one per line, e.g. \"loan-agreement\")",
            value="loan-agreement\nland-registry-extract",
        )

        legal_setup_confirmed = st.checkbox(
            "Legal setup confirmed",
            help="Confirms that origination and legal setup (loan agreement, land registry filing, etc.) "
            "have been completed off-chain. Required before the mortgage token can be minted.",
        )

        submitted = st.form_submit_button("Create Mortgage Token", type="primary")

    if submitted:
        if not (connected and contract is not None and owner_private_key):
            st.error("Missing node connection, contract address, or owner private key.")
        elif not legal_setup_confirmed:
            st.error("Legal setup must be confirmed before the mortgage token can be minted.")
        elif not (loan_agreement_id.strip() and land_registry_extract_id.strip()):
            st.error("Loan agreement ID and land registry extract ID are required.")
        else:
            try:
                account = w3.eth.account.from_key(owner_private_key)
                document_hashes = [
                    Web3.keccak(text=line.strip())
                    for line in document_text.splitlines()
                    if line.strip()
                ]
                terms = (
                    Web3.to_wei(principal_amount, "ether"),
                    currency,
                    int(time.mktime(maturity.timetuple())),
                    int(round(interest_rate_pct * 100)),
                )
                payment_mode_index = 0 if payment_mode == "SIC" else 1
                stablecoin_arg = (
                    Web3.to_checksum_address(clean_hex_input(stablecoin_address))
                    if stablecoin_address.strip()
                    else ZERO_ADDRESS
                )

                tx = contract.functions.createMortgage(
                    Web3.to_checksum_address(clean_hex_input(borrower)),
                    Web3.to_checksum_address(clean_hex_input(investor)),
                    document_hashes,
                    terms,
                    payment_mode_index,
                    stablecoin_arg,
                    (legal_setup_confirmed, loan_agreement_id.strip(), land_registry_extract_id.strip()),
                ).build_transaction(
                    {
                        "from": account.address,
                        "nonce": w3.eth.get_transaction_count(account.address),
                    }
                )
                signed = w3.eth.account.sign_transaction(tx, private_key=owner_private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                with st.spinner("Waiting for transaction receipt..."):
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                created_events = contract.events.MortgageCreated().process_receipt(receipt)
                if created_events:
                    mortgage_id = created_events[0]["args"]["mortgageId"]
                    st.success(f"Mortgage token #{mortgage_id} created and minted to {investor}.")
                else:
                    st.success("Transaction confirmed, but no MortgageCreated event was found.")
                st.markdown(f"**Tx hash:** `{tx_hash.hex()}`")
            except Exception as e:
                st.error(f"Transaction failed: {e}")

with tab_lookup:
    st.subheader("Look up an existing mortgage")

    if contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")
    else:
        mortgage_id = st.number_input("Mortgage ID", min_value=1, step=1, value=1)
        if st.button("Look up"):
            try:
                m = contract.functions.getMortgage(mortgage_id).call()
                holder = contract.functions.currentTokenholder(mortgage_id).call()
                doc_hashes = contract.functions.getDocumentHashes(mortgage_id).call()

                lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]
                payment_mode_labels = ["SIC", "Stablecoin"]

                st.markdown(f"**Current tokenholder:** `{holder}`")
                st.markdown(f"**Issuer:** `{m[1]}`")
                st.markdown(f"**Borrower:** `{m[2]}`")
                st.markdown(f"**Investor:** `{m[3]}`")
                st.markdown(f"**Principal:** {Web3.from_wei(m[4][0], 'ether')} {m[4][1]}")
                st.markdown(f"**Maturity date:** {datetime.fromtimestamp(m[4][2]).date()}")
                st.markdown(f"**Interest rate:** {m[4][3] / 100:.2f}%")
                st.markdown(f"**Payment mode:** {payment_mode_labels[m[5]]}")
                st.markdown(f"**Status:** {lifecycle_labels[m[7]]}")
                st.markdown(f"**Legal setup confirmed:** {'✅ yes' if m[8] else '❌ no'}")
                st.markdown(f"**Loan agreement ID:** {m[9] or 'none'}")
                st.markdown(f"**Land registry extract ID:** {m[10] or 'none'}")
                st.markdown(f"**Document hashes:** {[h.hex() for h in doc_hashes] or 'none'}")
            except Exception as e:
                st.error(f"Lookup failed: {e}")
