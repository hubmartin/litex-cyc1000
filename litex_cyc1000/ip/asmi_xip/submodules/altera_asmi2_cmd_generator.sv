// (C) 2001-2025 Altera Corporation. All rights reserved.
// Your use of Altera Corporation's design tools, logic functions and other 
// software and tools, and its AMPP partner logic functions, and any output 
// files from any of the foregoing (including device programming or simulation 
// files), and any associated documentation or information are expressly subject 
// to the terms and conditions of the Altera Program License Subscription 
// Agreement, Altera IP License Agreement, or other applicable 
// license agreement, including, without limitation, that your use is for the 
// sole purpose of programming logic devices manufactured by Altera and sold by 
// Altera or its authorized distributors.  Please refer to the applicable 
// agreement for further details.


// $File: //acds/main/ip/sopc/components/verification/altera_avalon_st_source_bfm/altera_avalon_st_source_bfm.sv $
// $Revision: #48 $
// $Date: 2015/07/23 $
// $Author: aferrucc $

`timescale 1 ps / 1 ps
module altera_asmi2_cmd_generator (
        input               clk,
        input               reset,

        input [1:0]         in_cmd_channel,
        input               in_cmd_eop,
        output logic        in_cmd_ready,
        input               in_cmd_sop,
        input [31:0]        in_cmd_data,
        input               in_cmd_valid,

        output logic [1:0]  out_cmd_channel,
        output logic        out_cmd_eop,
        input               out_cmd_ready,
        output logic        out_cmd_sop,
        output logic [7:0]  out_cmd_data,
        output logic        out_cmd_valid,

        input [7:0]         in_rsp_data,
        output logic        in_rsp_ready,
        input               in_rsp_valid,

        output logic [1:0]  out_rsp_channel,
        output logic [31:0] out_rsp_data,
        output logic        out_rsp_eop,
        input               out_rsp_ready,
        output logic        out_rsp_sop,
        output logic        out_rsp_valid,

        input [31:0]        addr_bytes_csr,
        input [31:0]        addr_bytes_xip,
        // Control signals to qspi interface component
        output logic [4:0]  dummy_cycles,
        output logic [3:0]  chip_select,
        output logic        require_rdata
    );

   // State machine
    typedef enum bit [8:0]
    {
        ST_IDLE             = 9'b000000001,
        ST_SEND_OPCODE      = 9'b000000010,
        ST_SEND_ADDR        = 9'b000000100,
        ST_SEND_DUMMY       = 9'b000001000,
        ST_SEND_DATA        = 9'b000010000,
        ST_WAIT_RSP         = 9'b000100000,
        ST_WAIT_BUFFER      = 9'b001000000,
        ST_SEND_DUMMY_RSP   = 9'b010000000,
        ST_COMPLETE         = 9'b100000000
     } t_state;
    t_state state, next_state;

    // +--------------------------------------------------
    // | Internal Signals
    // +--------------------------------------------------
    logic [3:0][7:0]    addr_mem;
    logic [1:0]         addr_cnt;
    logic [1:0]         addr_cnt_next;
    logic [31:0]        header_information;
    logic [1:0]         in_cmd_channel_reg;
    logic               has_addr;
    logic               is_4bytes_addr;
    logic               has_data_in;
    logic               has_data_out;
    logic               has_data_in_wire;
    logic               has_data_out_wire;
    logic               has_dummy;
    logic [7:0]         opcode;
    logic [4:0]         numb_dummy_cycles;
    logic [3:0]         chip_select_reg;
    logic [3:0]         chip_select_wire;
    
    logic [7:0]         numb_data_bytes;
    logic [7:0]         numb_data_bytes_round_up;
    logic               in_rsp_ready_adapt;
    logic [7:0]         csr_addr_0, csr_addr_1, csr_addr_2, csr_addr_3;
    logic [7:0]         xip_addr_0, xip_addr_1, xip_addr_2, xip_addr_3;
    
    logic [2:0]         buffer_cnt;
    logic [2:0]         buffer_cnt_next;
    logic               buffer_cnt_done;
    logic [1:0]         numb_addr_bytes;
    logic               addr_cnt_done;
    logic [7:0]         data_in_cnt;
    logic [7:0]         data_in_cnt_next;
    logic               data_in_cnt_done;
    logic [7:0]         data_out_cnt;
    logic [7:0]         data_out_cnt_next;
    logic               data_out_cnt_done;
    logic [7:0]         numb_data_bytes_in_cnt;
    logic [7:0]         numb_data_bytes_in_next;
    logic               last_data_word_in;
    logic               discard_rsp_pck;
    logic               last_word_detect;
    logic               in_cmd_eop_reg;
    logic               need_data_in;
    logic               need_data_out;
    
    // +--------------------------------------------------
    // | Decode Header
    // +--------------------------------------------------
    // |
    // register the header first
    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            header_information  <= '0;
            in_cmd_channel_reg  <= '0;
            in_cmd_eop_reg      <= '0;
        end
        else begin 
            if (in_cmd_valid && in_cmd_sop && in_cmd_ready) begin
                header_information <= in_cmd_data;
                in_cmd_channel_reg <= in_cmd_channel;
                in_cmd_eop_reg     <= in_cmd_eop; // use top detect end of packet
            end
        end
    end
    assign opcode             = header_information[7:0];
    assign has_addr           = header_information[8];
    assign is_4bytes_addr     = header_information[9];
    assign has_data_in        = header_information[10];
    assign has_data_out       = header_information[11];
    assign has_dummy          = header_information[12];
    assign numb_dummy_cycles  = header_information[17:13];
    assign numb_data_bytes    = header_information[26:18];
    assign chip_select        = header_information[30:27];
    assign has_data_in_wire   = header_information[10];
    assign has_data_out_wire  = header_information[11];

    // Process address byte
    assign csr_addr_0     = addr_bytes_csr[7:0];
    assign csr_addr_1     = addr_bytes_csr[15:8];
    assign csr_addr_2     = addr_bytes_csr[23:16];
    assign csr_addr_3     = addr_bytes_csr[31:24];
    assign xip_addr_0     = addr_bytes_xip[7:0];
    assign xip_addr_1     = addr_bytes_xip[15:8];
    assign xip_addr_2     = addr_bytes_xip[23:16];
    assign xip_addr_3     = addr_bytes_xip[31:24];
    assign dummy_cycles   = numb_dummy_cycles;
    // Note that swap the address byte.
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            addr_mem <= '{{8{1'b0}}, {8{1'b0}}, {8{1'b0}}, {8{1'b0}}};
        else begin 
            if (in_cmd_valid && in_cmd_sop && in_cmd_ready) begin
                // 2'b01 is the channel for XIP controller
                // 2'b10 is the channel for CST controller
                if (in_cmd_channel == 2'b10)
                    addr_mem <= {csr_addr_3, csr_addr_2, csr_addr_1, csr_addr_0};
                else
                    addr_mem <= {xip_addr_3, xip_addr_2, xip_addr_1, xip_addr_0};
            end
        end
    end

    // +--------------------------------------------------
    // | Address bytes counter
    // +--------------------------------------------------
    assign numb_addr_bytes = is_4bytes_addr ? 2'h3 : 2'h2;
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            addr_cnt <= '0;
        else begin
            if (state == ST_SEND_OPCODE)
                addr_cnt <= numb_addr_bytes;
            else
                addr_cnt <= addr_cnt_next;
        end
    end

    assign addr_cnt_done = ((addr_cnt == 0) & out_cmd_valid & out_cmd_ready);

    always_comb begin 
        addr_cnt_next = addr_cnt;
        if ((state == ST_SEND_ADDR) & out_cmd_valid & out_cmd_ready) begin
            addr_cnt_next = addr_cnt_next - 2'h1;
            if (addr_cnt_done)
                addr_cnt_next = numb_addr_bytes;
        end
    end
    
    // +--------------------------------------------------
    // | Buffer counter: just count few cycles then return
    // | fake response, make sure nothing sent in
    // +--------------------------------------------------
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            buffer_cnt <= '0;
        else
            buffer_cnt <= buffer_cnt_next;
    end
    assign buffer_cnt_done = (buffer_cnt == 3'b111);
   
    always_comb begin
        buffer_cnt_next = buffer_cnt;
        if (state == ST_WAIT_BUFFER) begin
            buffer_cnt_next = buffer_cnt_next + 4'h1;
            if (buffer_cnt_done)
                buffer_cnt_next = '0;
        end
    end

    // +--------------------------------------------------
    // | Write Data bytes counter
    // +--------------------------------------------------
    // Use this signal to discard the rsponse packet, the downstream component: qspi interface
    // might give extra packet, once the counter is done, discard all rsp pck, not go through adater
    // as well as stop the counters.
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            discard_rsp_pck <= '0;
        else begin
            if (data_out_cnt_done && (state == ST_WAIT_RSP))
                discard_rsp_pck <= 1;
            //if (in_cmd_valid && in_cmd_sop & in_cmd_ready && need_data_out)
            if (state == ST_IDLE)
                discard_rsp_pck <= 0;
        end
    end
    
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            data_in_cnt <= '0;
        else
            data_in_cnt <= data_in_cnt_next;
    end
    assign data_in_cnt_done = ((data_in_cnt == (numb_data_bytes - 4'h1)) & out_cmd_valid & out_cmd_ready);
    always_comb begin 
        data_in_cnt_next = data_in_cnt;
        if ((state == ST_SEND_DATA) & out_cmd_valid & out_cmd_ready) begin
        //if (!discard_rsp_pck && out_cmd_valid && out_cmd_ready) begin
            data_in_cnt_next = data_in_cnt_next + 4'h1;
            if (data_in_cnt_done)
                data_in_cnt_next = '0;
        end
    end
    // Round up the number of data bytes input, (see like in word unit), the input bytes
    // can be any number, round up to 32 bits. ex: controller can send 1, 2, 3 bytes -> round up to 4 bytes
    // if 21, 23 -> round up to 24.
    // This is used to find out when is the last data "word" is received, then the generator stops cmd_ready
    always_comb begin 
        if (numb_data_bytes[1] || numb_data_bytes[0])
            numb_data_bytes_round_up = {numb_data_bytes[7:2], 2'b00} + 3'b100;
        else
            numb_data_bytes_round_up = numb_data_bytes;
    end
    
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            numb_data_bytes_in_cnt <= '0;
        else
            numb_data_bytes_in_cnt <= numb_data_bytes_in_next;
    end
    assign last_data_word_in       = (numb_data_bytes_in_cnt == numb_data_bytes_round_up);

    always_comb begin 
        numb_data_bytes_in_next = numb_data_bytes_in_cnt;
        if (state != ST_IDLE) begin 
            if (has_data_in & in_cmd_valid & in_cmd_ready)
                numb_data_bytes_in_next = numb_data_bytes_in_next + 7'h4;
        end
        else
            numb_data_bytes_in_next = '0;
    end


    // +--------------------------------------------------
    // | Write Data bytes counter
    // +--------------------------------------------------
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            data_out_cnt <= '0;
        else
            data_out_cnt <= data_out_cnt_next;
    end
    assign data_out_cnt_done = ((data_out_cnt == (numb_data_bytes - 4'h1)) & in_rsp_valid & in_rsp_ready);
    always_comb begin 
        data_out_cnt_next = data_out_cnt;
        if ((state == ST_WAIT_RSP) & in_rsp_valid & in_rsp_ready) begin
            data_out_cnt_next = data_out_cnt_next + 4'h1;
            if (data_out_cnt_done)
                data_out_cnt_next = '0;
        end
    end




    logic [31:0]    adap_in_cmd_data;
    logic           adap_in_cmd_valid;
    logic           adap_in_cmd_ready;
    logic [7:0]     adap_out_cmd_data;
    logic           adap_out_cmd_valid;
    logic           adap_out_cmd_ready;


    // +--------------------------------------------------
    // | State Machine: update state
    // +--------------------------------------------------
    // |
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            state <= ST_IDLE;
        else
            state <= next_state;
    end

    // +--------------------------------------------------
    // | State Machine: next state condition
    // +--------------------------------------------------
    always_comb begin
        next_state  = ST_IDLE;
        case (state)
            ST_IDLE: begin
                next_state  = ST_IDLE;
                if (in_cmd_valid && in_cmd_sop)
                    next_state = ST_SEND_OPCODE;
            end
            ST_SEND_OPCODE: begin
                next_state  = ST_SEND_OPCODE;
                if (out_cmd_ready) begin
                    if (has_addr)
                        next_state = ST_SEND_ADDR;
                    else if (has_data_in)
                        next_state = ST_SEND_DATA;
                    else if (has_data_out)
                        next_state = ST_WAIT_RSP;
                    else
                        next_state = ST_WAIT_BUFFER;
                end
            end
            ST_SEND_ADDR: begin
                next_state = ST_SEND_ADDR;
                if (addr_cnt_done) begin 
                    if (has_data_in)
                        next_state = ST_SEND_DATA;
                    else if (has_data_out)
                        next_state = ST_WAIT_RSP;
                    else
                        next_state = ST_WAIT_BUFFER;     
                end
            end
            ST_SEND_DATA: begin
                next_state = ST_SEND_DATA;
                if (data_in_cnt_done) begin 
                    if (has_data_out)
                        next_state = ST_WAIT_RSP;
                    else
                        next_state = ST_WAIT_BUFFER;
                end
            end
            ST_WAIT_BUFFER: begin
                next_state = ST_WAIT_BUFFER;
                if (buffer_cnt_done)
                    next_state = ST_SEND_DUMMY_RSP;
            end
            ST_SEND_DUMMY_RSP: begin
                next_state = ST_SEND_DUMMY_RSP;
                if (out_rsp_ready)
                    next_state = ST_IDLE;
            end
            ST_WAIT_RSP: begin
                next_state = ST_WAIT_RSP;
                if (data_out_cnt_done)
                   next_state = ST_COMPLETE;
            end
            ST_COMPLETE: begin
                next_state = ST_COMPLETE;
                if (out_rsp_valid && out_rsp_eop)
                   next_state = ST_IDLE;
            end
        endcase // case (state)
    end // always_comb

    // +--------------------------------------------------
    // | State Machine: state outputs
    // +--------------------------------------------------
    always_comb begin
        out_cmd_valid       = '0;
        out_cmd_data        = '0;
        out_cmd_sop         = '0;
        out_cmd_eop         = '0;
        in_cmd_ready        = '0;
        case (state)
            ST_IDLE: begin
                out_cmd_valid       = '0;
                out_cmd_data        = '0;
                out_cmd_sop         = '0;
                out_cmd_eop         = '0;
                in_cmd_ready        = 1'b1;
            end
            ST_SEND_OPCODE: begin 
                out_cmd_valid       = 1'b1;
                out_cmd_data        = opcode;
                out_cmd_sop         = 1'b1;
                out_cmd_eop         = !has_addr & !has_data_in;
                in_cmd_ready        = '0;
            end
            ST_SEND_ADDR: begin 
                out_cmd_valid       = 1'b1;
                out_cmd_data        = addr_mem[addr_cnt];
                out_cmd_sop         = '0;
                out_cmd_eop         = !has_data_in & addr_cnt_done;
                //in_cmd_ready        = '0;
                //in_cmd_ready        = (state == ST_SEND_ADDR) && (addr_cnt == '0) && has_data_in && adap_in_cmd_ready;
                in_cmd_ready        = adap_in_cmd_ready && !last_word_detect;
            end
            ST_SEND_DATA: begin 
                out_cmd_valid       = adap_out_cmd_valid;
                out_cmd_data        = adap_out_cmd_data;
                out_cmd_sop         = '0;
                out_cmd_eop         = data_in_cnt_done;
                //in_cmd_ready        = adap_in_cmd_ready && !last_wrdata;
                // only allow data in if not last word.
                //in_cmd_ready        = adap_in_cmd_ready && !last_data_word_in;
                in_cmd_ready        = adap_in_cmd_ready && !last_word_detect;
            end
            ST_WAIT_BUFFER: begin
                out_cmd_valid       = '0;
                out_cmd_data        = '0;
                out_cmd_sop         = '0;
                out_cmd_eop         = '0;
                in_cmd_ready        = '0;
            end
            ST_SEND_DUMMY_RSP: begin 
                out_cmd_valid       = '0;
                out_cmd_data        = 32'h0;
                out_cmd_sop         = '0;
                out_cmd_eop         = '0;
                in_cmd_ready        = '0;
            end
            ST_WAIT_RSP: begin 
                out_cmd_valid       = '0;
                out_cmd_data        = 32'h0;
                out_cmd_sop         = '0;
                out_cmd_eop         = '0;
                in_cmd_ready        = '0;
            end
            ST_COMPLETE: begin 
                out_cmd_valid       = '0;
                out_cmd_data        = 32'h0;
                out_cmd_sop         = '0;
                out_cmd_eop         = '0;
                in_cmd_ready        = '0;
            end

        endcase // case (state)
    end

    // +--------------------------------------------------
    // | Output mapping
    // +--------------------------------------------------
    assign out_cmd_channel  = in_cmd_channel;
    //assign in_cmd_ready   = out_cmd_ready;
    assign in_rsp_ready     = in_rsp_ready_adapt;
    assign require_rdata    = (state == ST_IDLE) ? 1'b0 : has_data_out;

    logic adapt_8_32_sop;
    logic adapt_8_32_eop;
    logic adapt_8_32_valid;
    logic [31:0] adapt_8_32_data;

    logic internal_rsp_valid; // this is fake response
    logic internal_rsp_sop; // this is fake response
    logic internal_rsp_eop; // this is fake response
    assign internal_rsp_valid = (state == ST_SEND_DUMMY_RSP);
    assign internal_rsp_sop = (state == ST_SEND_DUMMY_RSP);
    assign internal_rsp_eop = (state == ST_SEND_DUMMY_RSP);
    assign out_rsp_channel  = in_cmd_channel_reg;
    assign out_rsp_valid    = internal_rsp_valid | adapt_8_32_valid;
    assign out_rsp_sop      = internal_rsp_sop | adapt_8_32_sop;
    assign out_rsp_eop      = internal_rsp_eop | adapt_8_32_eop;
    // If the adapter has data then use this or else zero
    assign out_rsp_data     = adapt_8_32_valid ? adapt_8_32_data : 32'h0;

    assign adap_in_cmd_data     = in_cmd_sop ? 32'h0 : in_cmd_data;
    //assign adap_in_cmd_valid    = in_cmd_sop ? 1'h0 : in_cmd_valid;
    
    logic has_data_in_reg;
    always @(posedge clk) begin
        if (reset)
            has_data_in_reg <= 1'b0;
        else begin
            if (out_cmd_valid && out_cmd_ready && (state == ST_SEND_OPCODE))
                has_data_in_reg <= has_data_in;
        end
    end
    //assign adap_in_cmd_valid    = in_cmd_valid;
    //assign adap_in_cmd_valid    = in_cmd_valid && has_data_in_reg;
    assign adap_out_cmd_ready   = (state == ST_SEND_DATA) & out_cmd_ready;
    assign adap_in_cmd_valid    = ((state == ST_SEND_ADDR) || (state == ST_SEND_DATA)) ? in_cmd_valid : 1'b0;


    logic sop_enable;
    logic in_rsp_sop;
    logic in_rsp_eop;

    assign in_rsp_sop    = sop_enable;
    assign in_rsp_eop    = data_out_cnt_done;
    always @(posedge clk) begin
        if (reset) begin
            sop_enable <= 1'b1;
        end
        else begin
            if (in_rsp_valid && in_rsp_ready) begin
                sop_enable <= 1'b0;
                if (in_rsp_eop)
                    sop_enable <= 1'b1;
            end
        end
    end


    assign need_data_in = in_cmd_sop ? has_data_in_wire : has_data_in;
    assign need_data_out = in_cmd_sop ? has_data_out_wire : has_data_out;

    always @(posedge clk) begin
        if (reset) begin
            last_word_detect <= 1'b0;
        end
        else begin
            //if (in_cmd_valid && in_cmd_ready && in_cmd_eop && (has_data_in || has_data_out)) 
            if (in_cmd_valid && in_cmd_ready && in_cmd_eop && (need_data_in || need_data_out)) 
            //if ((state == ST_PROCESS_HEADER) && (has_data_in || has_data_out)) 
                last_word_detect <= 1'b1;
            //if (state == ST_IDLE)
            if ((state == ST_SEND_DUMMY_RSP) || (state == ST_COMPLETE))
                    last_word_detect <= 1'b0;
        end
    end

    // +--------------------------------------------------
    // | 32 bits to 8 bits adapter - for command
    // +--------------------------------------------------    
    logic adapter_rst;
    //assign adapter_en = !(state == ST_SEND_DATA) && !((state == ST_SEND_ADDR) && (addr_cnt == '0));
    assign adapter_rst = (state == ST_IDLE);
        intel_asmi2_data_adapter_32_8 intel_asmi2_data_adapter_32_8_inst (
        .clk               (clk),           
        .reset             (reset || adapter_rst),     
        .in_data           (adap_in_cmd_data),           
        .in_valid          (adap_in_cmd_valid),          
        .in_ready          (adap_in_cmd_ready),          
        .out_data          (adap_out_cmd_data),          
        .out_valid         (adap_out_cmd_valid),         
        .out_ready         (adap_out_cmd_ready)
    );

    // +--------------------------------------------------
    // | 8 bits to 32 bits adapter - for response
    // +--------------------------------------------------    
    intel_asmi2_data_adapter_8_32 intel_asmi2_data_adapter_8_32_inst(
        .clk               (clk),           
        .reset             (reset || adapter_rst),
        //.reset             (reset || !(state == ST_WAIT_RSP)),
        .in_data           (in_rsp_data),
        .in_valid          (in_rsp_valid && (state == ST_WAIT_RSP)),
        //.in_valid          (in_rsp_valid && !discard_rsp_pck),
        // .in_valid         (in_rsp_valid),
        .in_ready          (in_rsp_ready_adapt),          
        .in_startofpacket  (in_rsp_sop),
        .in_endofpacket    (in_rsp_eop),
        .out_data          (adapt_8_32_data),          
        .out_valid         (adapt_8_32_valid),         
        .out_ready         (out_rsp_ready),
        .out_startofpacket (adapt_8_32_sop),
        .out_endofpacket   (adapt_8_32_eop)
    );


endmodule

 
