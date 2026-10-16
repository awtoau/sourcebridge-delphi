program ScalarLayout;

begin
  Writeln('Integer=', SizeOf(Integer));
  Writeln('Cardinal=', SizeOf(Cardinal));
  Writeln('AddSigned=', Integer(1) + Integer(2));
  Writeln('AddUnsigned=', Cardinal(1) + Cardinal(2));
end.
