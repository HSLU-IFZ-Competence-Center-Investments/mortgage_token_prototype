// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MortgageToken} from "../src/MortgageToken.sol";

contract MortgageTokenScript is Script {
    function run() external returns (MortgageToken token) {
        vm.startBroadcast();
        token = new MortgageToken(msg.sender);
        vm.stopBroadcast();

        console.log("MortgageToken deployed at:", address(token));
    }
}
