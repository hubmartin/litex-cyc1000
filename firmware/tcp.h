#ifndef __TCP_H
#define __TCP_H

#include <stdint.h>

/* TCP flags */
#define TCP_FIN  0x01
#define TCP_SYN  0x02
#define TCP_RST  0x04
#define TCP_PSH  0x08
#define TCP_ACK  0x10

/* TCP connection states */
#define TCP_STATE_LISTEN      0
#define TCP_STATE_SYN_RCVD    1
#define TCP_STATE_ESTABLISHED 2
#define TCP_STATE_FIN_WAIT_1  3
#define TCP_STATE_FIN_WAIT_2  4
#define TCP_STATE_CLOSING     5
#define TCP_STATE_CLOSED      6

/* Application-level receive callback: called when data arrives on an
   established connection.  Return value is ignored for now. */
typedef void (*tcp_app_callback)(uint32_t src_ip, uint16_t src_port,
                                 uint16_t dst_port,
                                 const void *data, uint16_t len);

void tcp_init(void);
void tcp_listen(uint16_t port, tcp_app_callback cb);
int  tcp_write(const void *data, uint16_t len);
void tcp_close(void);

#endif /* __TCP_H */
