import ipaddress, socket, struct, enum, re, os, socket, time, sys, requests
from network import models
from scapy.all import sr1, IP, UDP, DNS, DNSQR, DNSRR


class Protocol(enum.Enum):
    ARP = 0
    ICMP = 1

def device_lookup(mac : str):
    
    r = requests.get(f'https://macvendors.com/query/{mac}')

    if r.status_code == 200:
        return r.text if r.text != 'Not Found' else None
    

def nslookup(host : ipaddress._IPAddressBase, reverse : bool=False):

    try: 

        if reverse:

            ip = IP(dst='192.168.1.1')
            dns = DNS(rd=1, qd=DNSQR(qname=host.reverse_pointer, qtype='PTR'))

            response = sr1(ip / UDP() / dns, verbose=0, promisc=False)
            return response[DNS][DNSRR].rdata.decode()
            
        else:

            return socket.getaddrinfo(host, 0)[0][4][0]
        
    except Exception as e:
        print(f'{"Reverse" if reverse else ""} nslookup failed to resolve "{host}"', e)

def ping(dst : ipaddress._IPAddressBase):

    s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

    ip = models.IPHeader()
    ip.version = 4
    ip.length = 0x28
    ip.protocol = socket.IPPROTO_ICMP
    ip.ttl = 255
    ip.identifier = os.getpid() & 0xffff
    ip._src = default_interface(dst)
    ip._dst = dst.packed

    icmp = models.IcmpHeader()
    icmp.type = 8
    icmp.code = 0
    icmp.id = os.getpid() & 0xffff

    s.sendto(ip.pack() + icmp.pack(), (str(dst), 0))
    s.sendto(icmp.pack(), (str(dst), 0))

    start = time.time()
    data, addr = s.recvfrom(1024)
    s.close()

    return int((time.time() - start) * 1000)

def avg_rtt(dst : ipaddress._IPAddressBase, rounds : int=10):

    total_rtt = 0

    print(f'[INFO]: Calculating RTT Average...')
    for _ in range(rounds):

        total_rtt += ping(dst)

    print(f'[INFO]: Average RTT: {total_rtt / rounds} ms')

    return (total_rtt / rounds) + 100 # Average RTT + 100ms

def default_interface(dst : ipaddress._IPAddressBase) -> ipaddress._IPAddressBase:

    family = socket.AF_INET if dst.version == 4 else socket.AF_INET6

    s = socket.socket(family, socket.SOCK_DGRAM)
    s.connect((str(dst), 80))

    return is_valid_host(s.getsockname()[0])
    
def is_valid_domain(domain : str):

    r = re.compile('^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$')
    return r.match(domain)

def is_valid_host(host : str):

    try:
        return ipaddress.ip_address(host)
    except:
        if is_valid_domain(host):
            try:
                addr = socket.getaddrinfo(host, 0)
                return is_valid_host(addr[0][4][0])
            except Exception as e:
                print(f'[ERROR]: Failed to resolve {host}', e)
    
def is_valid_network(network : str):

    try:
        return ipaddress.ip_network(network)
    except:
        pass

def calculate_checksum(packet):

    if len(packet) % 2 == 1:
        packet += b'\0'

    data = struct.unpack('!%dH' % (len(packet) // 2), packet)
    
    checksum = sum(data)
    checksum += (checksum & 0xffff >> 16)
    checksum += (checksum >> 16)

    return ~checksum & 0xffff

def create_packet_icmp(src, dst):
        
        header = struct.pack('!bbHHh', 8, 0, 0, os.getpid() & 0xffff, 0)
        packet = struct.unpack(f'!%dH' % (len(header) // 2), header)

        checksum = sum(packet)
        carry = checksum >> 16

        while carry:
            checksum = (checksum & 0xffff) + carry
            carry = checksum & 0xff

        checksum = ~checksum & 0xffff

        packet = struct.pack('bbHHh', 8, 0, socket.htons(checksum), os.getpid() & 0xffff, 0)

        return packet