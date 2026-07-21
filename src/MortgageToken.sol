// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {ERC721} from "openzeppelin-contracts/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "openzeppelin-contracts/contracts/access/Ownable.sol";
import {IERC20} from "openzeppelin-contracts/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "openzeppelin-contracts/contracts/token/ERC20/utils/SafeERC20.sol";

/// @notice Each ERC-721 token represents one mortgage;
/// the current tokenholder is the ERC-721 owner of that token.
contract MortgageToken is ERC721, Ownable {
    using SafeERC20 for IERC20;

    enum LifecycleStatus {
        Created,
        Disbursed,
        Active,
        Matured,
        Repaid,
        Closed
    }

    enum PaymentStatus {
        Pending,
        Paid,
        Late,
        Missed
    }

    enum PaymentCategory {
        PurchasePrice,
        InterestPayment,
        PrincipalRedemption
    }

    struct MortgageTerms {
        uint256 principalAmount;
        string currency;
        uint256 maturityDate;
        uint256 interestRateBps;
    }

    struct LegalSetup {
        bool confirmed;
        string loanAgreementId;
        string landRegistryExtractId;
    }

    struct LoanDisbursement {
        bool confirmed;
        string disbursementReference;
    }

    struct PaymentRecord {
        uint256 dueDate;
        uint256 amount;
        PaymentStatus status;
        address payer;
        address recipient;
        uint256 timestamp;
        string fiatReference;
        string paymentReference;
        PaymentCategory category;
    }

    struct Mortgage {
        uint256 mortgageId;
        address issuer;
        string borrower;
        address investor; // set when transferTokenToInvestor is called; address(0) until then
        MortgageTerms terms;
        address stablecoinAddress;
        LifecycleStatus status;
        uint256 statusChangedAt;
        bool legalSetupConfirmed;
        string loanAgreementId;
        string landRegistryExtractId;
        bool loanDisbursementConfirmed;
        string disbursementReference;
        bool principalRepaymentConfirmed;
        string principalRepaymentReference;
    }

    uint256 private _nextMortgageId = 1;

    mapping(uint256 => Mortgage) private _mortgages;
    mapping(uint256 => bytes32[]) private _documentHashes;
    mapping(uint256 => PaymentRecord[]) private _paymentRecords;

    event MortgageCreated(uint256 indexed mortgageId, string borrower);
    event TokenTransferredToInvestor(uint256 indexed mortgageId, address indexed investor);
    event PurchasePriceSettled(uint256 indexed mortgageId, address indexed investor, uint256 purchasePrice);
    event PrincipalRepaymentConfirmed(uint256 indexed mortgageId, string repaymentReference);
    event TokenRedeemedAndBurned(uint256 indexed mortgageId, address indexed investor, uint256 principalPaymentAmount);
    event DocumentHashAdded(uint256 indexed mortgageId, bytes32 documentHash);
    event LifecycleStatusChanged(uint256 indexed mortgageId, LifecycleStatus previousStatus, LifecycleStatus newStatus);
    event PaymentScheduled(uint256 indexed mortgageId, uint256 indexed paymentIndex, uint256 dueDate, uint256 amount);
    event PaymentSettled(uint256 indexed mortgageId, uint256 indexed paymentIndex, address payer, address recipient, string fiatReference, string paymentReference, PaymentCategory category);
    event PaymentReferenceUpdated(uint256 indexed mortgageId, uint256 indexed paymentIndex, string paymentReference);
    event PaymentStatusUpdated(uint256 indexed mortgageId, uint256 indexed paymentIndex, PaymentStatus status);

    constructor(address initialOwner) ERC721("MortgageToken", "MORT") Ownable(initialOwner) {}

    /// @notice Mints a mortgage token to the issuer/processor (the caller). The investor
    /// is not yet known at this stage and is recorded later via transferTokenToInvestor.
    /// Off-chain origination and legal setup (e.g. loan agreement execution, land
    /// registry filing) must be confirmed complete via legalSetup_.confirmed, and loan
    /// disbursement (fiat via SIC) must be confirmed complete via
    /// loanDisbursement_.confirmed, before the token can be minted. Interest payments
    /// are always settled on-chain in the given stablecoin.
    function createMortgage(
        string calldata borrower_,
        bytes32[] calldata documentHashes_,
        MortgageTerms calldata terms_,
        address stablecoinAddress_,
        LegalSetup calldata legalSetup_,
        LoanDisbursement calldata loanDisbursement_
    ) external onlyOwner returns (uint256 mortgageId) {
        require(bytes(borrower_).length != 0, "borrower reference required");
        require(legalSetup_.confirmed, "legal setup must be confirmed before minting");
        require(bytes(legalSetup_.loanAgreementId).length != 0, "loan agreement ID required");
        require(bytes(legalSetup_.landRegistryExtractId).length != 0, "land registry extract ID required");
        require(loanDisbursement_.confirmed, "loan disbursement must be confirmed before minting");
        require(bytes(loanDisbursement_.disbursementReference).length != 0, "fiat payment reference for disbursement required");
        require(stablecoinAddress_ != address(0), "stablecoin address required");

        mortgageId = _nextMortgageId++;

        _mortgages[mortgageId] = Mortgage({
            mortgageId: mortgageId,
            issuer: msg.sender,
            borrower: borrower_,
            investor: address(0),
            terms: terms_,
            stablecoinAddress: stablecoinAddress_,
            status: LifecycleStatus.Created,
            statusChangedAt: block.timestamp,
            legalSetupConfirmed: legalSetup_.confirmed,
            loanAgreementId: legalSetup_.loanAgreementId,
            landRegistryExtractId: legalSetup_.landRegistryExtractId,
            loanDisbursementConfirmed: loanDisbursement_.confirmed,
            disbursementReference: loanDisbursement_.disbursementReference,
            principalRepaymentConfirmed: false,
            principalRepaymentReference: ""
        });

        _documentHashes[mortgageId] = documentHashes_;
        

        _safeMint(msg.sender, mortgageId);

        emit MortgageCreated(mortgageId, borrower_);
    }

    /// @notice Records the investor for this mortgage, pulls the investor's stablecoin
    /// purchase price (approved beforehand by the investor) and forwards it to the
    /// issuer/processor, then transfers the mortgage token from the issuer/processor
    /// to the investor and moves the mortgage into Active status.
    function transferTokenToInvestor(uint256 mortgageId, address investor_, uint256 purchasePrice_) external onlyOwner {
        Mortgage storage mortgage = _mortgages[mortgageId];
        require(mortgage.mortgageId != 0, "mortgage does not exist");
        require(ownerOf(mortgageId) == mortgage.issuer, "token already transferred to investor");
        require(investor_ != address(0), "investor is zero address");
        require(purchasePrice_ > 0, "purchase price must be greater than zero");

        mortgage.investor = investor_;

        IERC20(mortgage.stablecoinAddress).safeTransferFrom(mortgage.investor, mortgage.issuer, purchasePrice_);

        uint256 paymentIndex = _paymentRecords[mortgageId].length;
        _paymentRecords[mortgageId].push(
            PaymentRecord({
                dueDate: 0,
                amount: purchasePrice_,
                status: PaymentStatus.Paid,
                payer: mortgage.investor,
                recipient: mortgage.issuer,
                timestamp: block.timestamp,
                fiatReference: "",
                paymentReference: "",
                category: PaymentCategory.PurchasePrice
            })
        );

        _safeTransfer(mortgage.issuer, mortgage.investor, mortgageId, "");

        LifecycleStatus previousStatus = mortgage.status;
        mortgage.status = LifecycleStatus.Active;
        mortgage.statusChangedAt = block.timestamp;

        emit PurchasePriceSettled(mortgageId, mortgage.investor, purchasePrice_);
        emit PaymentSettled(mortgageId, paymentIndex, mortgage.investor, mortgage.issuer, "", "", PaymentCategory.PurchasePrice);
        emit TokenTransferredToInvestor(mortgageId, mortgage.investor);
        emit LifecycleStatusChanged(mortgageId, previousStatus, LifecycleStatus.Active);
    }

    /// @notice Records that the borrower's fiat interest payment was received via SIC
    /// (fiatPaymentReference_), and pulls the corresponding stablecoin interest payment
    /// from the issuer/processor (who must have approved this contract beforehand)
    /// forwarding it to the current tokenholder. Confirmation and payment are bundled
    /// into a single call since the issuer/processor is the one party performing both.
    /// The stablecoin payment reference isn't known until this call's own transaction
    /// hash exists, so it starts empty and must be filled in afterwards via
    /// updatePaymentReference.
    function payInterest(
        uint256 mortgageId,
        uint256 amount,
        string calldata fiatPaymentReference_
    ) external onlyOwner {
        Mortgage storage mortgage = _mortgages[mortgageId];
        require(mortgage.mortgageId != 0, "mortgage does not exist");
        require(mortgage.status == LifecycleStatus.Active, "mortgage not active");
        require(amount > 0, "amount must be greater than zero");
        require(bytes(fiatPaymentReference_).length != 0, "fiat payment reference required");

        address recipient = ownerOf(mortgageId);

        IERC20(mortgage.stablecoinAddress).safeTransferFrom(mortgage.issuer, recipient, amount);

        uint256 paymentIndex = _paymentRecords[mortgageId].length;
        _paymentRecords[mortgageId].push(
            PaymentRecord({
                dueDate: 0,
                amount: amount,
                status: PaymentStatus.Paid,
                payer: mortgage.issuer,
                recipient: recipient,
                timestamp: block.timestamp,
                fiatReference: fiatPaymentReference_,
                paymentReference: "",
                category: PaymentCategory.InterestPayment
            })
        );

        emit PaymentSettled(mortgageId, paymentIndex, mortgage.issuer, recipient, fiatPaymentReference_, "", PaymentCategory.InterestPayment);
    }

    /// @notice Fills in a payment record's stablecoin payment reference after the fact —
    /// used to record payInterest's own transaction hash as the reference, which isn't
    /// known until after that transaction has been signed and sent.
    function updatePaymentReference(uint256 mortgageId, uint256 paymentIndex, string calldata stablecoinPaymentReference_) external onlyOwner {
        require(paymentIndex < _paymentRecords[mortgageId].length, "payment record does not exist");

        _paymentRecords[mortgageId][paymentIndex].paymentReference = stablecoinPaymentReference_;

        emit PaymentReferenceUpdated(mortgageId, paymentIndex, stablecoinPaymentReference_);
    }

    /// @notice Records the reference to the fiat principal repayment conducted via
    /// SIC at maturity, and moves the mortgage into Repaid status. No funds move
    /// on-chain here — the SIC payment happens off-chain and this only confirms it.
    function confirmPrincipalRepayment(uint256 mortgageId, string calldata repaymentReference_) external onlyOwner {
        Mortgage storage mortgage = _mortgages[mortgageId];
        require(mortgage.mortgageId != 0, "mortgage does not exist");
        require(mortgage.status == LifecycleStatus.Active, "mortgage not active");
        require(block.timestamp >= mortgage.terms.maturityDate, "maturity date not reached");
        require(!mortgage.principalRepaymentConfirmed, "principal repayment already confirmed");
        require(bytes(repaymentReference_).length != 0, "fiat payment reference for repayment required");

        mortgage.principalRepaymentConfirmed = true;
        mortgage.principalRepaymentReference = repaymentReference_;

        LifecycleStatus previousStatus = mortgage.status;
        mortgage.status = LifecycleStatus.Repaid;
        mortgage.statusChangedAt = block.timestamp;

        emit PrincipalRepaymentConfirmed(mortgageId, repaymentReference_);
        emit LifecycleStatusChanged(mortgageId, previousStatus, LifecycleStatus.Repaid);
    }

    /// @notice Pulls the stablecoin principal redemption payment from the issuer/processor
    /// (who must have approved this contract beforehand) forwarding it to the current
    /// tokenholder, then burns the mortgage token and moves the mortgage into Closed
    /// status. Requires confirmPrincipalRepayment to have been called first.
    function redeemAndBurnToken(uint256 mortgageId, uint256 principalPaymentAmount_) external onlyOwner {
        Mortgage storage mortgage = _mortgages[mortgageId];
        require(mortgage.mortgageId != 0, "mortgage does not exist");
        require(mortgage.status == LifecycleStatus.Repaid, "principal repayment not confirmed");
        require(principalPaymentAmount_ > 0, "principal payment amount must be greater than zero");

        address recipient = ownerOf(mortgageId);

        IERC20(mortgage.stablecoinAddress).safeTransferFrom(mortgage.issuer, recipient, principalPaymentAmount_);

        uint256 paymentIndex = _paymentRecords[mortgageId].length;
        _paymentRecords[mortgageId].push(
            PaymentRecord({
                dueDate: 0,
                amount: principalPaymentAmount_,
                status: PaymentStatus.Paid,
                payer: mortgage.issuer,
                recipient: recipient,
                timestamp: block.timestamp,
                fiatReference: "",
                paymentReference: "",
                category: PaymentCategory.PrincipalRedemption
            })
        );

        _burn(mortgageId);

        LifecycleStatus previousStatus = mortgage.status;
        mortgage.status = LifecycleStatus.Closed;
        mortgage.statusChangedAt = block.timestamp;

        emit PaymentSettled(mortgageId, paymentIndex, mortgage.issuer, recipient, "", "", PaymentCategory.PrincipalRedemption);
        emit TokenRedeemedAndBurned(mortgageId, recipient, principalPaymentAmount_);
        emit LifecycleStatusChanged(mortgageId, previousStatus, LifecycleStatus.Closed);
    }

    function getMortgage(uint256 mortgageId) external view returns (Mortgage memory) {
        return _mortgages[mortgageId];
    }

    function getPaymentRecords(uint256 mortgageId) external view returns (PaymentRecord[] memory) {
        return _paymentRecords[mortgageId];
    }

    function getDocumentHashes(uint256 mortgageId) external view returns (bytes32[] memory) {
        return _documentHashes[mortgageId];
    }

    function currentTokenholder(uint256 mortgageId) external view returns (address) {
        return ownerOf(mortgageId);
    }
}
