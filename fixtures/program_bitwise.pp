program ProgramBitwise;

var
  a: longint;
  b: longint;
  c: longint;

begin
  a := 12;
  b := 10;
  c := a and b;
  writeln(c);
  if (c <> 8) then
    halt(1);
  c := a or b;
  writeln(c);
  if (c <> 14) then
    halt(2);
  c := a xor b;
  writeln(c);
  if (c <> 6) then
    halt(3);
  c := a + b;
  writeln(c);
  if (c <> 22) then
    halt(4);
  c := a - b;
  writeln(c);
  if (c <> 2) then
    halt(5);
  c := a * b;
  writeln(c);
  if (c <> 120) then
    halt(6);
end.
