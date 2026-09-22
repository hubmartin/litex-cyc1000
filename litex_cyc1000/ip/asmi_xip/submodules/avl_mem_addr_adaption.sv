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


`timescale 1ns / 1ns

module avl_mem_addr_adaption #(
    parameter ADDR_WIDTH    = 22,
    parameter ASMI_ADDR_WIDTH = 22
)(
    input                  clk,
    input                  reset,
                                                        
    // ports to access memory                   
    input                  avl_mem_write,
    input                  avl_mem_read,
    input [ADDR_WIDTH-1:0] avl_mem_addr,
    input [31:0]           avl_mem_wrdata,
    input [3:0]            avl_mem_byteenable,
    input [6:0]            avl_mem_burstcount,
    output [31:0]          avl_mem_rddata,
    output logic           avl_mem_rddata_valid,
    output logic           avl_mem_waitrequest,
    
    
    // ASMI PARALLEL interface
    output logic [31:0]    asmi_mem_addr, 
    output logic           asmi_mem_read, 
    input [31:0]           asmi_mem_rddata, 
    output logic           asmi_mem_write, 
    output logic [31:0]    asmi_mem_wrdata, 
    output logic [3:0]     asmi_mem_byteenable, 
    output logic [6:0]     asmi_mem_burstcount, 
    input                  asmi_mem_waitrequest, 
    input                  asmi_mem_rddata_valid

);

    // Do nothing, except adjust the address
     
    assign asmi_mem_addr        = {{31-ADDR_WIDTH{1'b0}}, avl_mem_addr};
    assign asmi_mem_read        = avl_mem_read;
    assign asmi_mem_write       = avl_mem_write;
    assign asmi_mem_wrdata      = avl_mem_wrdata;
    assign asmi_mem_byteenable  = avl_mem_byteenable;
    assign asmi_mem_burstcount  = avl_mem_burstcount;
    assign avl_mem_rddata       = asmi_mem_rddata;
    assign avl_mem_rddata_valid = asmi_mem_rddata_valid;
    assign avl_mem_waitrequest  = asmi_mem_waitrequest;

endmodule
