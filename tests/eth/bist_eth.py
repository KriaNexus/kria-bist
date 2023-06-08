# Copyright (C) 2023 Advanced Micro Devices, Inc.
# SPDX-License-Identifier: MIT

import os
import subprocess
import netifaces
import ipaddress
from pyroute2 import IPRoute
from ping3 import ping
import iperf3
import func_timeout
import glob
from time import sleep

remote_host_ip = '192.168.0.1'
remote_host_sfp_ip = '192.168.0.2'
static_ip_prefix = '192.168.0.1'

def eth_get_interface_speed(phy_addr, logger):
    """
    Get the eth interface and speed based on PHY address.

    Args:
            phy_addr: PHY address
            logger: Calling function's logger object

    Returns:
            string: eth interface
            float: Max speed in Gb/s
    """
    # Get list of interfaces
    interface_list = netifaces.interfaces()
    # Remove non-eth interfaces
    for interface in interface_list:
        if "eth" not in interface:
            interface_list.remove(interface)

    # Check for SFP case where PHY address is None
    if phy_addr is None:
        # Find eth interface without a PHY
        for interface in interface_list:
            if glob.glob("/sys/class/net/" + interface + "/phydev") == []:
                logger.debug("The SFP interface is: " + interface)
                # Default speed for SFP
                sfp_max_speed = 0.5 # Gbps
                return interface, sfp_max_speed

    # Check for matching PHY address
    for interface in interface_list:
        cmd = "ethtool " + interface
        ret = subprocess.run(cmd.split(' '), check=True, capture_output=True, text=True)
        if ret.returncode:
            logger.error("Failed to run " + cmd)
            return None, None
        output = ret.stdout
        if not output:
            logger.error("Failed to read ethtool output")
            return None, None
        phy_addr_string = "PHYAD: " + str(phy_addr)
        if phy_addr_string in output:
            speed = eth_get_speed(interface, logger)
            return interface, speed
    return None, None

def eth_get_speed(eth_interface, logger):
    """
    Get the max speed for the eth interface.

    Args:
            eth_interface: Name of eth interface
            logger: Calling function's logger object

    Returns:
            float: Max speed in Gb/s
    """
    cmd = "ethtool " + eth_interface
    ret = subprocess.run(cmd.split(' '), check=True, capture_output=True, text=True)
    if ret.returncode:
        logger.error("Failed to run " + cmd)
        return None
    output = ret.stdout
    if not output:
        logger.error("Failed to read ethtool output")
        return None
    # Get speed and convert to Gb/s
    try:
        speed_gbps = int(output.split('Speed: ')[1].split('Mb/s')[0])/1000
        logger.debug("The max speed for " + eth_interface + " is " + str(speed_gbps) + " Gb/s")
    except:
        logger.error("Unable to get max speed for " + eth_interface)
        return None
    return speed_gbps

def eth_setup(label, eth_interface, logger):
    """
    Verify that remote host IP and board IP are in the same subnet.
    If they aren't, add a static IP.

    Args:
            label: Test label
            eth_interface: Name of eth interface
            logger: Calling function's logger object

    Returns:
            interface_ip: Interface IP which is in the same subnet as remote host
            host_ip: Host IP of the appropriate interface
    """

    if "sfp" in label:
        # Override remote_host_sfp_ip if BIST_REMOTE_HOST_SFP_IP env var is defined
        global remote_host_sfp_ip
        remote_host_sfp_ip = os.getenv('BIST_REMOTE_HOST_SFP_IP', default=remote_host_sfp_ip)
        host_ip = remote_host_sfp_ip
        logger.info("The remote host SFP IP is currently set to " + remote_host_sfp_ip + " "
            "and can be changed by setting the BIST_REMOTE_HOST_SFP_IP environment variable.")
    else:
        # Override remote_host_ip if BIST_REMOTE_HOST_IP env var is defined
        global remote_host_ip
        remote_host_ip = os.getenv('BIST_REMOTE_HOST_IP', default=remote_host_ip)
        host_ip = remote_host_ip
        logger.info("The remote host IP is currently set to " + remote_host_ip + " "
            "and can be changed by setting the BIST_REMOTE_HOST_IP environment variable.")

    # Check if interface already has an IP in the same subnet as remote host
    try:
        interface_ips = [data['addr'] for data in netifaces.ifaddresses(eth_interface)[netifaces.AF_INET]]
    except:
        logger.info("No interface IP found for " + str(eth_interface))
        interface_ips = []

    if interface_ips != []:
        logger.debug(str(eth_interface) + " IPs: " + str(interface_ips))
        # Remove Host ID from interface ip and add /24 subnet mask
        ip_networks = [".".join(interface_ip.split('.')[:-1]) + '.0/24' for interface_ip in interface_ips]
        logger.debug("IP networks: " + str(ip_networks))
        for i in range(len(ip_networks)):
            if (ipaddress.ip_address(remote_host_ip) in ipaddress.ip_network(ip_networks[i])):
                logger.debug("Remote host IP " + remote_host_ip + " is in IP network " + ip_networks[i])
                return interface_ips[i], host_ip
            else:
                logger.debug("Remote host IP " + remote_host_ip + " is not in IP network " + ip_networks[i])

    # Assign static IP with last digit matching eth interface
    interface_ip = static_ip_prefix + eth_interface[-1]
    logger.info("Adding static IP " + interface_ip)
    ip = IPRoute()
    index = ip.link_lookup(ifname=eth_interface)[0]
    ip.addr('add', index=index, address=interface_ip, prefixlen=24)
    ip.close()
    return interface_ip, host_ip

def run_eth_ping_test(label, phy_addr, helpers):
    """
    Attempt to ping remote host

    Args:
            label: Test label
            phy_addr: PHY address
            helpers: Fixture for helper functions

    Returns:
            bool: True/False
    """
    logger = helpers.logger_init(label)
    logger.start_test()

    eth_interface, _ = eth_get_interface_speed(phy_addr, logger)
    if eth_interface is None:
        logger.error("Failed to get eth interface")
        return False

    _, host_ip = eth_setup(label, eth_interface, logger)

    logger.info("Pinging remote host " + host_ip)
    ping_result = ping(host_ip, interface=eth_interface)
    logger.info("Delay: " + str(ping_result))

    # ping returns delay if successful, False otherwise
    if ping_result:
        return True
    else:
        return False

def run_eth_perf_test(label, phy_addr, helpers):
    """
    Perf test with remote host as the server

    Args:
            label: Test label
            phy_addr: PHY address
            helpers: Fixture for helper functions

    Returns:
            bool: True/False
    """
    logger = helpers.logger_init(label)
    logger.start_test()

    eth_interface, max_speed_gbps = eth_get_interface_speed(phy_addr, logger)
    if eth_interface is None or max_speed_gbps is None:
        logger.error("Failed to get eth interface and speed")
        return False

    interface_ip, host_ip = eth_setup(label, eth_interface, logger)

    client = iperf3.Client()
    client.duration = 1
    client.server_hostname = host_ip
    client.port = 5201
    client.bind_address = interface_ip
    logger.debug("Client bind address: " + str(client.bind_address))
    try:
        perf_timeout = 3 # seconds
        perf_result = int(func_timeout.func_timeout(perf_timeout, client.run).sent_Mbps)/1000
    except func_timeout.FunctionTimedOut:
        sleep(0.05) # Short delay to prevent unwanted prints to console
        os.dup2(client._stdout_fd, 1) # Redirect output to console
        logger.error("iperf3 test timed out for interface " + str(eth_interface) + ". "
            "Please ensure the remote host IP is correct and an iperf3 server is running on the remote host.")
        return False
    except AttributeError as e:
        logger.error("iperf3 failed to measure bitrate. "
            "Please ensure the remote host IP is correct and an iperf3 server is running on the remote host.")
        return False
    logger.info("Measured bitrate: " + str(perf_result) + " Gbits/sec")

    # Check if measured bitrate is above threshold
    perf_speed_threshold = 0.8
    if perf_result >= perf_speed_threshold*max_speed_gbps:
        return True
    else:
        logger.error("The measured bitrate is lower than " + str(int(perf_speed_threshold*100)) + "% of the "
            "max bitrate of " + str(max_speed_gbps) + " Gbits/sec")
        return False
