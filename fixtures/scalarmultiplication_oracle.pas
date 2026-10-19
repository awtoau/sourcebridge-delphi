program ScalarMultiplicationOracle;

{$mode objfpc}{$H+}

function MulSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left * Right;
end;

function MulUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left * Right;
end;

begin
  Writeln('SignedOverflow=', MulSigned(High(Integer), 2));
  Writeln('UnsignedOverflow=', MulUnsigned(High(Cardinal), 2));
end.
