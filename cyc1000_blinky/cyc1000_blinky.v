module cyc1000_blinky (
    input  wire       clk12,
    output reg  [7:0] user_led
);
    // 12 MHz / 2^23 gives one visibly new LED about every 0.70 seconds.
    reg [22:0] counter = 23'd0;
    reg [2:0]  position = 3'd0;

    always @(posedge clk12) begin
        counter <= counter + 1'b1;
        if (&counter)
            position <= position + 1'b1;
    end

    // CYC1000 user LEDs are active-high.
    always @(*) user_led = (8'b00000001 << position);
endmodule
