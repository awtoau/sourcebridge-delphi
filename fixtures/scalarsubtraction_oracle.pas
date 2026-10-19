program ScalarSubtractionOracle;

{$mode objfpc}{$H+}

function SubSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left - Right;
end;

function SubUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left - Right;
end;

begin
  Writeln('SignedUnderflow=', SubSigned(Low(Integer), 1));
  Writeln('UnsignedUnderflow=', SubUnsigned(0, 1));
end.
