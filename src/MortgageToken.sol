// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {ERC721} from "openzeppelin-contracts/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "openzeppelin-contracts/contracts/access/Ownable.sol";

/// @notice Each ERC-721 token represents one mortgage;
/// the current tokenholder is the ERC-721 owner of that token.
contract MortgageToken is ERC721, Ownable {
    enum PaymentMode {
        SIC,
        Stablecoin
    }

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

    struct MortgageTerms {
        uint256 principalAmount;
        string currency;
        uint256 maturityDate;
        uint256 interestRateBps;
    }

    struct PaymentRecord {
        uint256 dueDate;
        uint256 amount;
        PaymentStatus status;
        address payer;
        address recipient;
        uint256 timestamp;
        string paymentReference;
    }

    struct Mortgage {
        uint256 mortgageId;
        address issuer;
        address borrower;
        address investor;
        MortgageTerms terms;
        PaymentMode paymentMode;
        address stablecoinAddress;
        LifecycleStatus status;
    }

    uint256 private _nextMortgageId = 1;

    mapping(uint256 => Mortgage) private _mortgages;
    mapping(uint256 => bytes32[]) private _documentHashes;
    mapping(uint256 => PaymentRecord[]) private _paymentRecords;

    event MortgageCreated(uint256 indexed mortgageId, address indexed borrower, address indexed investor);
    event DocumentHashAdded(uint256 indexed mortgageId, bytes32 documentHash);
    event LifecycleStatusChanged(uint256 indexed mortgageId, LifecycleStatus previousStatus, LifecycleStatus newStatus);
    event PaymentScheduled(uint256 indexed mortgageId, uint256 indexed paymentIndex, uint256 dueDate, uint256 amount);
    event PaymentSettled(uint256 indexed mortgageId, uint256 indexed paymentIndex, address payer, address recipient, string paymentReference);
    event PaymentStatusUpdated(uint256 indexed mortgageId, uint256 indexed paymentIndex, PaymentStatus status);

    constructor(address initialOwner) ERC721("MortgageToken", "MORT") Ownable(initialOwner) {}

    function createMortgage(
        address borrower_,
        address investor_,
        bytes32[] calldata documentHashes_,
        MortgageTerms calldata terms_,
        PaymentMode paymentMode_,
        address stablecoinAddress_
    ) external onlyOwner returns (uint256 mortgageId) {
        require(borrower_ != address(0), "borrower is zero address");
        require(investor_ != address(0), "investor is zero address");
        if (paymentMode_ == PaymentMode.Stablecoin) {
            require(stablecoinAddress_ != address(0), "stablecoin address required");
        } else {
            require(stablecoinAddress_ == address(0), "stablecoin address not allowed for SIC mode");
        }

        mortgageId = _nextMortgageId++;

        _mortgages[mortgageId] = Mortgage({
            mortgageId: mortgageId,
            issuer: msg.sender,
            borrower: borrower_,
            investor: investor_,
            terms: terms_,
            paymentMode: paymentMode_,
            stablecoinAddress: stablecoinAddress_,
            status: LifecycleStatus.Created
        });

        _documentHashes[mortgageId] = documentHashes_;

        _safeMint(investor_, mortgageId);

        emit MortgageCreated(mortgageId, borrower_, investor_);
    }
}
