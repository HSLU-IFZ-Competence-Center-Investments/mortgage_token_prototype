// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MortgageToken} from "../src/MortgageToken.sol";
import {Ownable} from "openzeppelin-contracts/contracts/access/Ownable.sol";

contract MortgageTokenTest is Test {
    MortgageToken public token;

    address public owner = address(this);
    address public borrower = address(0xB0B);
    address public investor = address(0x1A5706);
    address public stablecoin = address(0x57AB1);

    function setUp() public {
        token = new MortgageToken(owner);
    }

    function _sicTerms() internal view returns (MortgageToken.MortgageTerms memory) {
        return MortgageToken.MortgageTerms({
            principalAmount: 500_000 ether,
            currency: "CHF",
            maturityDate: block.timestamp + 365 days,
            interestRateBps: 250
        });
    }

    function test_createMortgage_mintsTokenToInvestor() public {
        bytes32[] memory documentHashes = new bytes32[](2);
        documentHashes[0] = keccak256("loan-agreement");
        documentHashes[1] = keccak256("land-registry-extract");

        uint256 mortgageId = token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0)
        );

        assertEq(mortgageId, 1);
        assertEq(token.ownerOf(mortgageId), investor);
        assertEq(token.currentTokenholder(mortgageId), investor);

        MortgageToken.Mortgage memory mortgage = token.getMortgage(mortgageId);
        assertEq(mortgage.mortgageId, mortgageId);
        assertEq(mortgage.issuer, owner);
        assertEq(mortgage.borrower, borrower);
        assertEq(mortgage.investor, investor);
        assertEq(mortgage.terms.principalAmount, 500_000 ether);
        assertEq(mortgage.terms.currency, "CHF");
        assertEq(mortgage.terms.interestRateBps, 250);
        assertEq(mortgage.stablecoinAddress, address(0));
        assertEq(uint8(mortgage.paymentMode), uint8(MortgageToken.PaymentMode.SIC));
        assertEq(uint8(mortgage.status), uint8(MortgageToken.LifecycleStatus.Created));

        bytes32[] memory storedHashes = token.getDocumentHashes(mortgageId);
        assertEq(storedHashes.length, 2);
        assertEq(storedHashes[0], documentHashes[0]);
        assertEq(storedHashes[1], documentHashes[1]);
    }

    function test_createMortgage_incrementsMortgageId() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        uint256 firstId = token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0)
        );
        uint256 secondId = token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0)
        );

        assertEq(firstId, 1);
        assertEq(secondId, 2);
    }

    function test_createMortgage_stablecoinMode_storesStablecoinAddress() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        uint256 mortgageId = token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.Stablecoin, stablecoin
        );

        MortgageToken.Mortgage memory mortgage = token.getMortgage(mortgageId);
        assertEq(uint8(mortgage.paymentMode), uint8(MortgageToken.PaymentMode.Stablecoin));
        assertEq(mortgage.stablecoinAddress, stablecoin);
    }

    function test_createMortgage_emitsMortgageCreatedEvent() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        vm.expectEmit(true, true, true, true);
        emit MortgageToken.MortgageCreated(1, borrower, investor);

        token.createMortgage(borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0));
    }

    function test_createMortgage_revertsWhenBorrowerIsZeroAddress() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        vm.expectRevert("borrower is zero address");
        token.createMortgage(
            address(0), investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0)
        );
    }

    function test_createMortgage_revertsWhenInvestorIsZeroAddress() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        vm.expectRevert("investor is zero address");
        token.createMortgage(
            borrower, address(0), documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0)
        );
    }

    function test_createMortgage_revertsWhenStablecoinModeMissingAddress() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        vm.expectRevert("stablecoin address required");
        token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.Stablecoin, address(0)
        );
    }

    function test_createMortgage_revertsWhenSicModeHasStablecoinAddress() public {
        bytes32[] memory documentHashes = new bytes32[](0);

        vm.expectRevert("stablecoin address not allowed for SIC mode");
        token.createMortgage(
            borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, stablecoin
        );
    }

    function test_createMortgage_revertsWhenCalledByNonOwner() public {
        bytes32[] memory documentHashes = new bytes32[](0);
        address stranger = address(0xDEAD);

        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger));
        token.createMortgage(borrower, investor, documentHashes, _sicTerms(), MortgageToken.PaymentMode.SIC, address(0));
    }
}
