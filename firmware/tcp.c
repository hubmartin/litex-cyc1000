/*
 * Minimal TCP state-machine for LiteX / CYC1000
 *
 * Supports exactly ONE concurrent connection (8 KB SRAM budget).
 * Handles: SYN → SYN+ACK → ESTABLISHED → data rx/tx → FIN handshake.
 * No retransmission, no window scaling, no out-of-order reassembly.
 */

#include <stdio.h>
#include <string.h>

#include <libliteeth/inet.h>
#include <libliteeth/udp.h>

#include "tcp.h"

/* ------------------------------------------------------------------ */
/* Internal state for the single connection                           */
/* ------------------------------------------------------------------ */

static int       tcp_state;
static uint32_t  remote_ip;
static uint16_t  remote_port;
static uint16_t  local_port;
static uint32_t  local_seq;   /* our next sequence number */
static uint32_t  remote_seq;  /* next expected from peer  */
static tcp_app_callback app_cb;

/* We listen on one port at a time. */
static uint16_t  listen_port;
static tcp_app_callback listen_cb;

/* ------------------------------------------------------------------ */
/* Pseudo-header for TCP checksum                                     */
/* ------------------------------------------------------------------ */

struct tcp_pseudo {
	uint32_t src_ip;
	uint32_t dst_ip;
	uint8_t  zero;
	uint8_t  proto;
	uint16_t tcp_len;
} __attribute__((packed));

/* ------------------------------------------------------------------ */
/* Send a TCP segment (flags only, or with payload).                  */
/* ------------------------------------------------------------------ */

static void tcp_send(uint8_t flags, const void *payload, uint16_t payload_len)
{
	uint8_t *txraw = eth_get_tx_buffer();

	/* Offsets inside the raw buffer — must match ethernet_frame layout */
	struct ethernet_header *eth = (struct ethernet_header *)txraw;
	struct ip_header *ip  = (struct ip_header *)(eth + 1);
	struct tcp_header *tcp = (struct tcp_header *)(ip + 1);
	uint8_t *data = (uint8_t *)(tcp + 1);

	uint16_t tcp_total = sizeof(struct tcp_header) + payload_len;
	uint16_t ip_total  = sizeof(struct ip_header) + tcp_total;

	/* Ethernet */
	/* We reuse the source MAC from the last received frame as destmac.
	   ARP is already resolved by the libliteeth layer for IP traffic. */
	/* For simplicity we just fill with broadcast; the switch/NIC on the
	   other side will accept it since we're replying to an existing
	   connection that already went through ARP. Actually let's look up
	   properly: we have the remote_ip cached. BUT on this tiny system we
	   don't have a proper ARP table accessible. The trick: the incoming
	   frame's src-mac is still in the RX buffer. We grab it here. */

	/* Actually the simplest correct approach: since process_frame already
	   did ARP, let's just set the fields ourselves. */
	{
		/* Grab the src MAC from the RX buffer that triggered us.
		   eth_get_tx_buffer() points to a DIFFERENT slot, so the RX
		   slot is still intact at this point. */
		/* We get our own MAC from the helper. For the dest MAC we
		   peek at the received packet's ethernet_header.srcmac.
		   The RX buffer is at ETHMAC_BASE + rxslot*SLOT_SIZE, but
		   we don't have direct rxslot access. Instead, we store
		   the remote MAC when we get the SYN. */
	}

	/* We'll store remote MAC at SYN time — see tcp_rx_handler */
	extern uint8_t tcp_remote_mac[6];

	eth_fill_header(eth, tcp_remote_mac, eth_get_my_mac(), 0x0800);

	/* IP */
	ip->version          = 0x45;
	ip->diff_services    = 0;
	ip->total_length     = htons(ip_total);
	ip->identification   = 0;
	ip->fragment_offset  = htons(0x4000); /* Don't Fragment */
	ip->ttl              = 64;
	ip->proto            = 0x06; /* TCP */
	ip->checksum         = 0;
	ip->src_ip           = htonl(eth_get_my_ip());
	ip->dst_ip           = htonl(remote_ip);
	ip->checksum         = htons(eth_ip_checksum(0, ip, sizeof(struct ip_header), 1));

	/* TCP */
	tcp->src_port    = htons(local_port);
	tcp->dst_port    = htons(remote_port);
	tcp->seq_num     = htonl(local_seq);
	tcp->ack_num     = htonl(remote_seq);
	tcp->data_offset = 0x50; /* 5 words, no options */
	tcp->flags       = flags;
	tcp->window      = htons(1024);
	tcp->checksum    = 0;
	tcp->urgent      = 0;

	if (payload && payload_len > 0) {
		memcpy(data, payload, payload_len);
	}

	/* TCP checksum over pseudo-header + TCP header + payload */
	{
		struct tcp_pseudo ph;
		uint32_t r;

		ph.src_ip  = htonl(eth_get_my_ip());
		ph.dst_ip  = htonl(remote_ip);
		ph.zero    = 0;
		ph.proto   = 0x06;
		ph.tcp_len = htons(tcp_total);

		r = eth_ip_checksum(0, &ph, sizeof(ph), 0);
		r = eth_ip_checksum(r, tcp, tcp_total, 1);
		tcp->checksum = htons(r);
	}

	int total = sizeof(struct ethernet_header) + ip_total;
	eth_set_tx_len(total);
	eth_send_packet();

	/* Advance local_seq for data bytes and SYN/FIN (which consume 1 seq) */
	if (flags & TCP_SYN) local_seq++;
	if (flags & TCP_FIN) local_seq++;
	local_seq += payload_len;
}

/* ------------------------------------------------------------------ */
/* Send data on the current established connection                    */
/* ------------------------------------------------------------------ */

int tcp_write(const void *data, uint16_t len)
{
	if (tcp_state != TCP_STATE_ESTABLISHED)
		return -1;
	/* Clamp to a safe MTU (slot size minus headers) */
	if (len > 1460)
		len = 1460;
	tcp_send(TCP_ACK | TCP_PSH, data, len);
	return len;
}

/* Close the connection from our side */
void tcp_close(void)
{
	if (tcp_state == TCP_STATE_ESTABLISHED) {
		tcp_send(TCP_FIN | TCP_ACK, NULL, 0);
		tcp_state = TCP_STATE_FIN_WAIT_1;
	}
}

/* ------------------------------------------------------------------ */
/* Remote MAC storage (filled on SYN receive)                         */
/* ------------------------------------------------------------------ */

uint8_t tcp_remote_mac[6];

/* ------------------------------------------------------------------ */
/* RX handler — registered as tcp_callback with libliteeth             */
/* ------------------------------------------------------------------ */

static void tcp_rx_handler(uint32_t src_ip, struct tcp_frame *frame,
                           uint32_t raw_len)
{
	uint16_t src_port = ntohs(frame->tcp.src_port);
	uint16_t dst_port = ntohs(frame->tcp.dst_port);
	uint8_t  flags    = frame->tcp.flags;

	/* TCP header length in bytes */
	uint8_t tcp_hdr_len = (frame->tcp.data_offset >> 4) * 4;
	uint16_t ip_total   = ntohs(frame->ip.total_length);
	int payload_len     = ip_total - sizeof(struct ip_header) - tcp_hdr_len;
	if (payload_len < 0) payload_len = 0;
	char *payload = ((char *)&frame->tcp) + tcp_hdr_len;

	/* ---- RST from peer: reset immediately ---- */
	if (flags & TCP_RST) {
		if (tcp_state != TCP_STATE_LISTEN)
			tcp_state = TCP_STATE_LISTEN;
		return;
	}

	switch (tcp_state) {

	case TCP_STATE_LISTEN:
		if ((flags & TCP_SYN) && dst_port == listen_port) {
			/* Store remote MAC from the RX frame.
			   The ethernet_header sits right before the ip_header
			   in the receive buffer. */
			struct ethernet_header *rxeth =
				(struct ethernet_header *)
				((uint8_t *)&frame->ip - sizeof(struct ethernet_header));
			memcpy(tcp_remote_mac, rxeth->srcmac, 6);

			remote_ip   = src_ip;
			remote_port = src_port;
			local_port  = dst_port;
			remote_seq  = ntohl(frame->tcp.seq_num) + 1;
			local_seq   = 1000; /* arbitrary ISN */
			app_cb      = listen_cb;

			tcp_send(TCP_SYN | TCP_ACK, NULL, 0);
			tcp_state = TCP_STATE_SYN_RCVD;
		}
		break;

	case TCP_STATE_SYN_RCVD:
		if ((flags & TCP_ACK) &&
		    src_ip == remote_ip && src_port == remote_port) {
			tcp_state = TCP_STATE_ESTABLISHED;
		}
		break;

	case TCP_STATE_ESTABLISHED:
		if (src_ip != remote_ip || src_port != remote_port)
			break;

		/* ACK incoming data */
		if (payload_len > 0) {
			remote_seq = ntohl(frame->tcp.seq_num) + payload_len;
			/* Deliver to application */
			if (app_cb)
				app_cb(src_ip, src_port, dst_port,
				       payload, payload_len);
		}

		if (flags & TCP_FIN) {
			remote_seq = ntohl(frame->tcp.seq_num) + payload_len + 1;
			tcp_send(TCP_ACK, NULL, 0);
			tcp_send(TCP_FIN | TCP_ACK, NULL, 0);
			tcp_state = TCP_STATE_CLOSED;
		}
		break;

	case TCP_STATE_FIN_WAIT_1:
		if (src_ip != remote_ip || src_port != remote_port)
			break;
		if (flags & TCP_ACK) {
			if (flags & TCP_FIN) {
				remote_seq = ntohl(frame->tcp.seq_num) + 1;
				tcp_send(TCP_ACK, NULL, 0);
				tcp_state = TCP_STATE_CLOSED;
			} else {
				tcp_state = TCP_STATE_FIN_WAIT_2;
			}
		}
		break;

	case TCP_STATE_FIN_WAIT_2:
		if (src_ip != remote_ip || src_port != remote_port)
			break;
		if (flags & TCP_FIN) {
			remote_seq = ntohl(frame->tcp.seq_num) + 1;
			tcp_send(TCP_ACK, NULL, 0);
			tcp_state = TCP_STATE_CLOSED;
		}
		break;

	case TCP_STATE_CLOSED:
		/* After a brief dwell, go back to listening */
		tcp_state = TCP_STATE_LISTEN;
		break;
	}
}

/* ------------------------------------------------------------------ */
/* Public API                                                         */
/* ------------------------------------------------------------------ */

void tcp_init(void)
{
	tcp_state   = TCP_STATE_LISTEN;
	listen_port = 0;
	listen_cb   = NULL;
	app_cb      = NULL;
	tcp_set_callback(tcp_rx_handler);
}

void tcp_listen(uint16_t port, tcp_app_callback cb)
{
	listen_port = port;
	listen_cb   = cb;
	tcp_state   = TCP_STATE_LISTEN;
}
