program ScalarBitwiseAndOracle;

{$mode objfpc}{$H+}

function BitAndSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left and Right;
end;

function BitAndUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left and Right;
end;

begin
  Writeln('bitandsigned(12,10)=', BitAndSigned(12, 10));
  Writeln('bitandsigned(-1,255)=', BitAndSigned(-1, 255));
  Writeln('bitandunsigned(240,15)=', BitAndUnsigned(240, 15));
end.
