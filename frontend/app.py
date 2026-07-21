import json
import time
from datetime import date, datetime
from pathlib import Path

import streamlit as st
from web3 import Web3

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_PATH = ROOT / "out" / "MortgageToken.sol" / "MortgageToken.json"
STATE_PATH = Path(__file__).resolve().parent / ".frontend_state.json"

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

st.set_page_config(page_title="Mortgage Token Demo", page_icon="\U0001F3E0", layout="centered")


def clean_hex_input(value: str) -> str:
    """Strip whitespace and stray quote characters from a pasted hex string
    (private key or address), which are commonly copied in by accident."""
    return value.strip().strip("'\"").strip()


def format_status_timestamp(unix_timestamp: int) -> str:
    return datetime.fromtimestamp(unix_timestamp).strftime("%H:%M %d-%m-%Y")


def require_success(receipt) -> None:
    """web3 doesn't raise when a transaction reverts; wait_for_transaction_receipt
    still returns a receipt with status 0. Surface that as an error instead of
    silently treating it like a successful call with no matching event."""
    if receipt.get("status") == 0:
        raise RuntimeError(
            f"Transaction reverted on-chain (tx {receipt['transactionHash'].hex()}). "
            "Check that the mortgage is in the right state and the account calling it has permission."
        )


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

    contract = None
    if connected and contract_address:
        try:
            abi = load_abi()
            contract = w3.eth.contract(address=Web3.to_checksum_address(clean_hex_input(contract_address)), abi=abi)
            owner = contract.functions.owner().call()
            st.markdown(f"**Contract owner:** `{owner}`")
        except Exception as e:
            st.error(f"Could not load contract: {e}")

    st.header("Mint Test Stablecoins")
    st.caption(
        "Only works against a MockStablecoin with an open mint() function. "
        "Real stablecoins (e.g. testnet USDC) will reject this."
    )
    mint_stablecoin_address = st.text_input(
        "Stablecoin address", value=saved_state.get("mint_stablecoin_address", ""), key="mint_stablecoin_address"
    )
    save_state(mint_stablecoin_address=mint_stablecoin_address)
    mint_signer_key = clean_hex_input(
        st.text_input(
            "Signer private key",
            type="password",
            help="Any account can call mint() on the mock — this just pays the gas.",
            key="mint_signer_key",
        )
    )
    mint_recipient = st.text_input("Mint to address", key="mint_recipient")
    mint_amount = st.number_input("Mint amount", min_value=0.0, value=10000.0, step=100.0, key="mint_amount")
    if st.button("Mint", key="mint_button"):
        if not (connected and mint_stablecoin_address.strip() and mint_signer_key and mint_recipient.strip()):
            st.error("Missing node connection, stablecoin address, signer private key, or recipient address.")
        else:
            try:
                mint_stablecoin = w3.eth.contract(
                    address=Web3.to_checksum_address(clean_hex_input(mint_stablecoin_address)), abi=ERC20_ABI
                )
                try:
                    mint_decimals = mint_stablecoin.functions.decimals().call()
                except Exception:
                    mint_decimals = 18
                mint_account = w3.eth.account.from_key(mint_signer_key)
                mint_units = int(round(mint_amount * (10**mint_decimals)))
                mint_tx = mint_stablecoin.functions.mint(
                    Web3.to_checksum_address(clean_hex_input(mint_recipient)), mint_units
                ).build_transaction(
                    {
                        "from": mint_account.address,
                        "nonce": w3.eth.get_transaction_count(mint_account.address),
                    }
                )
                signed_mint = w3.eth.account.sign_transaction(mint_tx, private_key=mint_signer_key)
                mint_hash = w3.eth.send_raw_transaction(signed_mint.raw_transaction)
                with st.spinner("Minting..."):
                    mint_receipt = w3.eth.wait_for_transaction_receipt(mint_hash)
                require_success(mint_receipt)
                st.success(f"Minted {mint_amount} to {mint_recipient}.")
            except Exception as e:
                st.error(f"Mint failed: {e}")

    st.header("Check Balance")
    st.caption("Reads the raw on-chain balance directly via the RPC — no MetaMask import or network needed.")
    balance_stablecoin_address = st.text_input(
        "Stablecoin address",
        value=saved_state.get("mint_stablecoin_address", ""),
        key="balance_stablecoin_address",
    )
    balance_account_address = st.text_input("Account address", key="balance_account_address")
    if st.button("Check Balance", key="check_balance_button"):
        if not (connected and balance_stablecoin_address.strip() and balance_account_address.strip()):
            st.error("Missing node connection, stablecoin address, or account address.")
        else:
            try:
                balance_stablecoin = w3.eth.contract(
                    address=Web3.to_checksum_address(clean_hex_input(balance_stablecoin_address)), abi=ERC20_ABI
                )
                try:
                    balance_decimals = balance_stablecoin.functions.decimals().call()
                    balance_symbol = balance_stablecoin.functions.symbol().call()
                except Exception:
                    balance_decimals = 18
                    balance_symbol = ""
                raw_balance = balance_stablecoin.functions.balanceOf(
                    Web3.to_checksum_address(clean_hex_input(balance_account_address))
                ).call()
                st.success(f"Balance: {raw_balance / (10**balance_decimals)} {balance_symbol}".strip())
            except Exception as e:
                st.error(f"Balance check failed: {e}")

tab_create, tab_transfer, tab_pay, tab_repay, tab_redeem, tab_lookup = st.tabs(
    ["Create Mortgage", "Transfer to Investor", "Pay Interest", "Confirm Repayment", "Redeem & Burn", "Look Up Mortgage"]
)

with tab_create:
    st.subheader("Create a new mortgage token")

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    with st.form("create_mortgage_form"):
        borrower = st.text_input(
            "Borrower reference",
            value="Peter Müller",
            help="An off-chain identifier for the borrower (e.g. a name or customer ID). "
            "The borrower has no blockchain address — they never interact with the contract; "
            "this is a reference field only.",
        )

        col3, col4 = st.columns(2)
        with col3:
            principal_amount = st.number_input("Principal amount", min_value=0.0, value=500000.0, step=1000.0)
        with col4:
            currency = st.text_input("Currency", value="CHF")

        col5, col6 = st.columns(2)
        with col5:
            maturity = st.date_input(
                "Maturity date",
                value=date.today(),
                help="Defaults to today so the mortgage is immediately eligible for principal repayment "
                "confirmation — handy for testing. Pick a future date for a realistic mortgage.",
            )
        with col6:
            interest_rate_pct = st.number_input("Interest rate (%)", min_value=0.0, value=2.5, step=0.1)

        stablecoin_address = st.text_input(
            "Stablecoin address", help="ERC-20 stablecoin used to settle interest payments on-chain."
        )

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

        disbursement_reference = st.text_input(
            "Fiat payment reference for disbursement",
            help="SIC payment reference for the fiat loan disbursement to the borrower.",
        )
        loan_disbursement_confirmed = st.checkbox(
            "Loan disbursement confirmed",
            help="Confirms that the fiat loan disbursement to the borrower (via SIC) has been completed off-chain. "
            "Required before the mortgage token can be minted.",
        )

        submitted = st.form_submit_button("Create Mortgage Token", type="primary")

    if submitted:
        if not (connected and contract is not None and owner_private_key):
            st.error("Missing node connection, contract address, or owner private key.")
        elif not legal_setup_confirmed:
            st.error("Legal setup must be confirmed before the mortgage token can be minted.")
        elif not borrower.strip():
            st.error("Borrower reference is required.")
        elif not (loan_agreement_id.strip() and land_registry_extract_id.strip()):
            st.error("Loan agreement ID and land registry extract ID are required.")
        elif not loan_disbursement_confirmed:
            st.error("Loan disbursement must be confirmed before the mortgage token can be minted.")
        elif not disbursement_reference.strip():
            st.error("Fiat payment reference for disbursement is required.")
        elif not stablecoin_address.strip():
            st.error("Stablecoin address is required.")
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
                tx = contract.functions.createMortgage(
                    borrower.strip(),
                    document_hashes,
                    terms,
                    Web3.to_checksum_address(clean_hex_input(stablecoin_address)),
                    (legal_setup_confirmed, loan_agreement_id.strip(), land_registry_extract_id.strip()),
                    (loan_disbursement_confirmed, disbursement_reference.strip()),
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
                require_success(receipt)

                created_events = contract.events.MortgageCreated().process_receipt(receipt)
                if created_events:
                    mortgage_id = created_events[0]["args"]["mortgageId"]
                    st.success(
                        f"Mortgage token #{mortgage_id} created and minted to the issuer ({account.address}). "
                        "Use the \"Transfer to Investor\" tab to transfer it to the investor."
                    )
                else:
                    st.success("Transaction confirmed, but no MortgageCreated event was found.")
                st.markdown(f"**Tx hash:** `{tx_hash.hex()}`")
            except Exception as e:
                st.error(f"Transaction failed: {e}")

with tab_transfer:
    st.subheader("Settle purchase and transfer token")
    st.caption(
        "Pulls the investor's stablecoin purchase price (the investor must approve this contract "
        "beforehand) and forwards it to the issuer/processor, then transfers the mortgage token from "
        "the issuer/processor to the investor."
    )

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    transfer_mortgage_id = st.number_input("Mortgage ID", min_value=1, step=1, value=1, key="transfer_mortgage_id")

    transfer_stablecoin = None
    transfer_stablecoin_decimals = 18
    default_purchase_price = 0.0
    if contract is not None:
        try:
            m = contract.functions.getMortgage(transfer_mortgage_id).call()
            holder = contract.functions.currentTokenholder(transfer_mortgage_id).call()
            lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]
            st.markdown(f"**Current tokenholder:** `{holder}`")
            st.markdown(f"**Issuer:** `{m[1]}`")
            st.markdown(f"**Investor:** `{m[3]}`")
            st.markdown(f"**Status:** {lifecycle_labels[m[6]]} ({format_status_timestamp(m[7])})")

            transfer_stablecoin = w3.eth.contract(address=Web3.to_checksum_address(m[5]), abi=ERC20_ABI)
            try:
                transfer_stablecoin_decimals = transfer_stablecoin.functions.decimals().call()
                stablecoin_symbol = transfer_stablecoin.functions.symbol().call()
                st.markdown(f"**Stablecoin:** {stablecoin_symbol} ({transfer_stablecoin_decimals} decimals)")
            except Exception:
                st.info("Could not read decimals/symbol from the stablecoin contract; assuming 18 decimals.")

            # principalAmount was entered as a human-readable number and stored via to_wei(..., "ether"),
            # i.e. always scaled by 1e18 regardless of the stablecoin's actual decimals — recover that
            # human number here and use it as the default (par) purchase price.
            default_purchase_price = m[4][0] / (10**18)
        except Exception as e:
            st.error(f"Could not load mortgage: {e}")

    purchase_price = st.number_input(
        "Purchase price", min_value=0.0, value=default_purchase_price, step=1000.0, key="purchase_price"
    )
    investor_address_input = st.text_input(
        "Investor address",
        help="The investor's address, recorded on-chain as the mortgage's investor. Must match the "
        "address derived from the investor private key below.",
        key="investor_address",
    )
    investor_private_key = clean_hex_input(
        st.text_input(
            "Investor private key",
            type="password",
            help="Used to sign the stablecoin approval; the investor must approve this contract "
            "to spend the purchase price before it can be pulled.",
            key="investor_private_key",
        )
    )

    if st.button("Settle Purchase and Transfer", type="primary"):
        if not (
            connected
            and contract is not None
            and transfer_stablecoin is not None
            and owner_private_key
            and investor_address_input.strip()
            and investor_private_key
        ):
            st.error("Missing node connection, contract address, owner private key, investor address, or investor private key.")
        elif purchase_price <= 0:
            st.error("Purchase price must be greater than zero.")
        else:
            try:
                owner_account = w3.eth.account.from_key(owner_private_key)
                investor_account = w3.eth.account.from_key(investor_private_key)
                investor_address = Web3.to_checksum_address(clean_hex_input(investor_address_input))
                if investor_address != investor_account.address:
                    st.error(
                        f"Investor address ({investor_address}) does not match the address derived "
                        f"from the investor private key ({investor_account.address})."
                    )
                    st.stop()
                purchase_price_units = int(round(purchase_price * (10**transfer_stablecoin_decimals)))

                allowance = transfer_stablecoin.functions.allowance(investor_account.address, contract.address).call()
                if allowance < purchase_price_units:
                    approve_tx = transfer_stablecoin.functions.approve(
                        contract.address, purchase_price_units
                    ).build_transaction(
                        {
                            "from": investor_account.address,
                            "nonce": w3.eth.get_transaction_count(investor_account.address),
                        }
                    )
                    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=investor_private_key)
                    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                    with st.spinner("Approving stablecoin spend..."):
                        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash)
                    require_success(approve_receipt)

                tx = contract.functions.transferTokenToInvestor(
                    transfer_mortgage_id, investor_account.address, purchase_price_units
                ).build_transaction(
                    {
                        "from": owner_account.address,
                        "nonce": w3.eth.get_transaction_count(owner_account.address),
                    }
                )
                signed = w3.eth.account.sign_transaction(tx, private_key=owner_private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                with st.spinner("Waiting for transaction receipt..."):
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                require_success(receipt)

                transferred_events = contract.events.TokenTransferredToInvestor().process_receipt(receipt)
                if transferred_events:
                    investor_addr = transferred_events[0]["args"]["investor"]
                    st.success(
                        f"Purchase price of {purchase_price} settled and mortgage token #{transfer_mortgage_id} "
                        f"transferred to investor {investor_addr}."
                    )
                else:
                    st.success("Transaction confirmed, but no TokenTransferredToInvestor event was found.")
                st.markdown(f"**Tx hash:** `{tx_hash.hex()}`")
            except Exception as e:
                st.error(f"Transaction failed: {e}")

with tab_pay:
    st.subheader("Pay stablecoin interest")
    st.caption(
        "Records that the borrower's fiat interest payment was received via SIC, and pulls the "
        "corresponding stablecoin interest payment from the issuer/processor's wallet, forwarding it "
        "to the current tokenholder."
    )

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    pay_mortgage_id = st.number_input("Mortgage ID", min_value=1, step=1, value=1, key="pay_mortgage_id")

    stablecoin = None
    stablecoin_decimals = 18
    m = None
    if contract is not None:
        try:
            m = contract.functions.getMortgage(pay_mortgage_id).call()
            holder = contract.functions.currentTokenholder(pay_mortgage_id).call()
            lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]
            st.markdown(f"**Borrower:** `{m[2]}`")
            st.markdown(f"**Current tokenholder (recipient):** `{holder}`")
            st.markdown(f"**Status:** {lifecycle_labels[m[6]]} ({format_status_timestamp(m[7])})")
            st.markdown(f"**Stablecoin address:** `{m[5]}`")

            stablecoin = w3.eth.contract(address=Web3.to_checksum_address(m[5]), abi=ERC20_ABI)
            try:
                stablecoin_decimals = stablecoin.functions.decimals().call()
                stablecoin_symbol = stablecoin.functions.symbol().call()
                st.markdown(f"**Stablecoin:** {stablecoin_symbol} ({stablecoin_decimals} decimals)")
            except Exception:
                st.info("Could not read decimals/symbol from the stablecoin contract; assuming 18 decimals.")
        except Exception as e:
            st.error(f"Could not load mortgage: {e}")

    st.caption("Uses the owner/issuer private key from the sidebar — payInterest is issuer/processor-only.")
    interest_amount = st.number_input("Interest amount", min_value=0.0, value=1000.0, step=10.0, key="interest_amount")
    fiat_payment_reference = st.text_input("Fiat payment reference (borrower's SIC payment)", key="fiat_payment_reference")

    if st.button("Pay Interest", type="primary"):
        if not (connected and contract is not None and stablecoin is not None and owner_private_key):
            st.error("Missing node connection, contract address, or owner private key.")
        elif not fiat_payment_reference.strip():
            st.error("Fiat payment reference is required.")
        elif interest_amount <= 0:
            st.error("Interest amount must be greater than zero.")
        else:
            try:
                account = w3.eth.account.from_key(owner_private_key)
                amount_units = int(round(interest_amount * (10**stablecoin_decimals)))

                allowance = stablecoin.functions.allowance(account.address, contract.address).call()
                if allowance < amount_units:
                    approve_tx = stablecoin.functions.approve(contract.address, amount_units).build_transaction(
                        {
                            "from": account.address,
                            "nonce": w3.eth.get_transaction_count(account.address),
                        }
                    )
                    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=owner_private_key)
                    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                    with st.spinner("Approving stablecoin spend..."):
                        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash)
                    require_success(approve_receipt)

                tx = contract.functions.payInterest(
                    pay_mortgage_id, amount_units, fiat_payment_reference.strip()
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
                require_success(receipt)

                settled_events = contract.events.PaymentSettled().process_receipt(receipt)
                if settled_events:
                    args = settled_events[0]["args"]
                    payment_index = args["paymentIndex"]

                    update_tx = contract.functions.updatePaymentReference(
                        pay_mortgage_id, payment_index, tx_hash.hex()
                    ).build_transaction(
                        {
                            "from": account.address,
                            "nonce": w3.eth.get_transaction_count(account.address),
                        }
                    )
                    signed_update = w3.eth.account.sign_transaction(update_tx, private_key=owner_private_key)
                    update_hash = w3.eth.send_raw_transaction(signed_update.raw_transaction)
                    with st.spinner("Recording payment reference..."):
                        update_receipt = w3.eth.wait_for_transaction_receipt(update_hash)
                    require_success(update_receipt)

                    st.success(
                        f"Interest payment #{payment_index} of {interest_amount} settled to {args['recipient']}."
                    )
                else:
                    st.success("Transaction confirmed, but no PaymentSettled event was found.")
                st.markdown(f"**Tx hash:** `{tx_hash.hex()}`")
            except Exception as e:
                st.error(f"Transaction failed: {e}")

with tab_repay:
    st.subheader("Confirm principal repayment")
    st.caption(
        "Records the reference to the fiat principal repayment conducted via SIC at maturity. "
        "No funds move on-chain here — this only confirms an off-chain payment and moves the "
        "mortgage into Repaid status."
    )

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    repay_mortgage_id = st.number_input("Mortgage ID", min_value=1, step=1, value=1, key="repay_mortgage_id")

    if contract is not None:
        try:
            m = contract.functions.getMortgage(repay_mortgage_id).call()
            lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]
            st.markdown(f"**Status:** {lifecycle_labels[m[6]]} ({format_status_timestamp(m[7])})")
            st.markdown(f"**Maturity date:** {datetime.fromtimestamp(m[4][2]).date()}")
            st.markdown(f"**Principal repayment confirmed:** {'✅ yes' if m[13] else '❌ no'}")
        except Exception as e:
            st.error(f"Could not load mortgage: {e}")

    repayment_reference = st.text_input(
        "Fiat payment reference for repayment", help="SIC payment reference for the fiat principal repayment."
    )

    if st.button("Confirm Repayment", type="primary"):
        if not (connected and contract is not None and owner_private_key):
            st.error("Missing node connection, contract address, or owner private key.")
        elif not repayment_reference.strip():
            st.error("Fiat payment reference for repayment is required.")
        else:
            try:
                account = w3.eth.account.from_key(owner_private_key)
                tx = contract.functions.confirmPrincipalRepayment(
                    repay_mortgage_id, repayment_reference.strip()
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
                require_success(receipt)

                confirmed_events = contract.events.PrincipalRepaymentConfirmed().process_receipt(receipt)
                if confirmed_events:
                    st.success(f"Principal repayment confirmed for mortgage #{repay_mortgage_id}.")
                else:
                    st.success("Transaction confirmed, but no PrincipalRepaymentConfirmed event was found.")
                st.markdown(f"**Tx hash:** `{tx_hash.hex()}`")
            except Exception as e:
                st.error(f"Transaction failed: {e}")

with tab_redeem:
    st.subheader("Redeem and burn token")
    st.caption(
        "Pulls the stablecoin principal redemption payment from the issuer/processor's wallet, forwards "
        "it to the current tokenholder, then burns the mortgage token. Requires principal repayment to "
        "have already been confirmed on the \"Confirm Repayment\" tab."
    )

    if not connected:
        st.warning("Connect to a running node (e.g. `anvil`) via the sidebar first.")
    elif contract is None:
        st.warning("Enter a deployed contract address in the sidebar.")

    redeem_mortgage_id = st.number_input("Mortgage ID", min_value=1, step=1, value=1, key="redeem_mortgage_id")

    redeem_stablecoin = None
    redeem_stablecoin_decimals = 18
    default_principal_payment = 0.0
    if contract is not None:
        try:
            m = contract.functions.getMortgage(redeem_mortgage_id).call()
            holder = contract.functions.currentTokenholder(redeem_mortgage_id).call()
            lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]
            st.markdown(f"**Current tokenholder (recipient):** `{holder}`")
            st.markdown(f"**Status:** {lifecycle_labels[m[6]]} ({format_status_timestamp(m[7])})")
            st.markdown(f"**Principal repayment confirmed:** {'✅ yes' if m[13] else '❌ no'}")

            redeem_stablecoin = w3.eth.contract(address=Web3.to_checksum_address(m[5]), abi=ERC20_ABI)
            try:
                redeem_stablecoin_decimals = redeem_stablecoin.functions.decimals().call()
                stablecoin_symbol = redeem_stablecoin.functions.symbol().call()
                st.markdown(f"**Stablecoin:** {stablecoin_symbol} ({redeem_stablecoin_decimals} decimals)")
            except Exception:
                st.info("Could not read decimals/symbol from the stablecoin contract; assuming 18 decimals.")

            # principalAmount was entered as a human-readable number and stored via to_wei(..., "ether"),
            # i.e. always scaled by 1e18 regardless of the stablecoin's actual decimals.
            default_principal_payment = m[4][0] / (10**18)
        except Exception as e:
            st.error(f"Could not load mortgage: {e}")

    principal_payment_amount = st.number_input(
        "Principal payment amount",
        min_value=0.0,
        value=default_principal_payment,
        step=1000.0,
        key="principal_payment_amount",
    )

    if st.button("Redeem and Burn Token", type="primary"):
        if not (connected and contract is not None and redeem_stablecoin is not None and owner_private_key):
            st.error("Missing node connection, contract address, or owner private key.")
        elif principal_payment_amount <= 0:
            st.error("Principal payment amount must be greater than zero.")
        else:
            try:
                account = w3.eth.account.from_key(owner_private_key)
                principal_units = int(round(principal_payment_amount * (10**redeem_stablecoin_decimals)))

                allowance = redeem_stablecoin.functions.allowance(account.address, contract.address).call()
                if allowance < principal_units:
                    approve_tx = redeem_stablecoin.functions.approve(
                        contract.address, principal_units
                    ).build_transaction(
                        {
                            "from": account.address,
                            "nonce": w3.eth.get_transaction_count(account.address),
                        }
                    )
                    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=owner_private_key)
                    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                    with st.spinner("Approving stablecoin spend..."):
                        approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash)
                    require_success(approve_receipt)

                tx = contract.functions.redeemAndBurnToken(
                    redeem_mortgage_id, principal_units
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
                require_success(receipt)

                redeemed_events = contract.events.TokenRedeemedAndBurned().process_receipt(receipt)
                if redeemed_events:
                    args = redeemed_events[0]["args"]
                    st.success(
                        f"Mortgage token #{redeem_mortgage_id} redeemed ({principal_payment_amount} paid to "
                        f"{args['investor']}) and burned."
                    )
                else:
                    st.success("Transaction confirmed, but no TokenRedeemedAndBurned event was found.")
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
                payment_records = contract.functions.getPaymentRecords(mortgage_id).call()

                lifecycle_labels = ["Created", "Disbursed", "Active", "Matured", "Repaid", "Closed"]

                st.markdown(f"**Current tokenholder:** `{holder}`")
                st.markdown(f"**Issuer:** `{m[1]}`")
                st.markdown(f"**Borrower:** `{m[2]}`")
                st.markdown(f"**Investor:** `{m[3]}`")
                st.markdown(f"**Principal:** {Web3.from_wei(m[4][0], 'ether')} {m[4][1]}")
                st.markdown(f"**Maturity date:** {datetime.fromtimestamp(m[4][2]).date()}")
                st.markdown(f"**Interest rate:** {m[4][3] / 100:.2f}%")
                st.markdown(f"**Stablecoin address:** `{m[5]}`")
                st.markdown(f"**Status:** {lifecycle_labels[m[6]]} ({format_status_timestamp(m[7])})")
                st.markdown(f"**Legal setup confirmed:** {'✅ yes' if m[8] else '❌ no'}")
                st.markdown(f"**Loan agreement ID:** {m[9] or 'none'}")
                st.markdown(f"**Land registry extract ID:** {m[10] or 'none'}")
                st.markdown(f"**Loan disbursement confirmed:** {'✅ yes' if m[11] else '❌ no'}")
                st.markdown(f"**Fiat payment reference for disbursement:** {m[12] or 'none'}")
                st.markdown(f"**Principal repayment confirmed:** {'✅ yes' if m[13] else '❌ no'}")
                st.markdown(f"**Fiat payment reference for repayment:** {m[14] or 'none'}")
                st.markdown(f"**Document hashes:** {[h.hex() for h in doc_hashes] or 'none'}")

                payment_status_labels = ["Pending", "Paid", "Late", "Missed"]
                payment_category_labels = ["Purchase Price", "Interest Payment", "Principal Redemption"]
                lookup_decimals = 18
                if m[5] != "0x0000000000000000000000000000000000000000":
                    try:
                        lookup_decimals = w3.eth.contract(
                            address=Web3.to_checksum_address(m[5]), abi=ERC20_ABI
                        ).functions.decimals().call()
                    except Exception:
                        pass

                st.markdown(f"**Payment records:** {len(payment_records) or 'none'}")
                for i, record in enumerate(payment_records):
                    amount_display = record[1] / (10**lookup_decimals)
                    st.markdown(
                        f"- #{i} [{payment_category_labels[record[8]]}]: {amount_display} at "
                        f"{format_status_timestamp(record[5])} — {payment_status_labels[record[2]]}, "
                        f"payer `{record[3]}`, recipient `{record[4]}`, "
                        f"fiat ref \"{record[6]}\", stablecoin ref \"{record[7]}\""
                    )
            except Exception as e:
                st.error(f"Lookup failed: {e}")
