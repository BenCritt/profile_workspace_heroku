import ipaddress

def calculate_subnet_details(ip_input: str, cidr_input: str):
    """
    Takes an IP address and a CIDR suffix (e.g. "192.168.1.5" and "24").
    Returns a dictionary of subnet details or an error message.
    """
    try:
        # Combine IP and CIDR (e.g., "192.168.1.5/24")
        network_str = f"{ip_input}/{cidr_input}"
        
        # strict=False allows passing a host IP (192.168.1.5) and getting the network (192.168.1.0)
        network = ipaddress.ip_network(network_str, strict=False)
        interface = ipaddress.ip_interface(network_str)
        
        results = {
            "ip_address": str(interface.ip),
            "network_address": str(network.network_address),
            "cidr_notation": str(network),
            "netmask": str(network.netmask),
            "wildcard_mask": str(network.hostmask),
            "total_hosts": network.num_addresses,
            "is_private": network.is_private,
            "version": network.version,
        }

        # IPv4 Specific Calculations
        if network.version == 4:
            results["usable_hosts"] = max(0, network.num_addresses - 2)
            results["broadcast_address"] = str(network.broadcast_address)
            
            # Binary representation
            # Convert netmask to binary string (32 chars)
            netmask_int = int(network.netmask)
            results["binary_netmask"] = f"{netmask_int:032b}"
            
            # Determine Class (Standard Architecture)
            first_octet = int(str(network.network_address).split('.')[0])
            if 1 <= first_octet <= 126:
                results["class"] = "A"
            elif 128 <= first_octet <= 191:
                results["class"] = "B"
            elif 192 <= first_octet <= 223:
                results["class"] = "C"
            elif 224 <= first_octet <= 239:
                results["class"] = "D (Multicast)"
            else:
                results["class"] = "E (Experimental)"

            # Host Range
            if network.num_addresses > 1:
                results["host_range_start"] = str(network.network_address + 1)
                results["host_range_end"] = str(network.broadcast_address - 1)
            else:
                results["host_range_start"] = "N/A"
                results["host_range_end"] = "N/A"

        # IPv6 Specifics (Simpler, as concepts like broadcast don't apply the same way)
        else:
            results["usable_hosts"] = "Extremely Large"
            results["broadcast_address"] = "N/A (IPv6 uses Multicast)"
            results["class"] = "N/A"
            results["binary_netmask"] = "N/A"
            results["host_range_start"] = str(network[1]) if network.num_addresses > 1 else "N/A"
            results["host_range_end"] = str(network[-1]) if network.num_addresses > 1 else "N/A"

        return results, None

    except ValueError as e:
        return None, f"Invalid Network: {str(e)}"
    except Exception as e:
        return None, f"Calculation Error: {str(e)}"