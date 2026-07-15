// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MortgageToken} from "../src/MortgageToken.sol";
import {MockStablecoin} from "../src/MockStablecoin.sol";

contract MortgageTokenScript is Script {
    function run() external returns (MortgageToken token, MockStablecoin stablecoin) {
        vm.startBroadcast();
        token = new MortgageToken(msg.sender);
        stablecoin = new MockStablecoin("HSLU USD", "hslUSD", 6);
        vm.stopBroadcast();

        console.log("MortgageToken deployed at:", address(token));
        console.log("MockStablecoin deployed at:", address(stablecoin));
    }
}
