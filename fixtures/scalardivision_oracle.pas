program ScalarDivisionOracle;

{$mode objfpc}{$H+}

function DivSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left div Right;
end;

function DivUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left div Right;
end;

begin
  Writeln('divsigned(7,2)=', DivSigned(7, 2));
  Writeln('divsigned(-7,2)=', DivSigned(-7, 2));
  Writeln('divunsigned(100,7)=', DivUnsigned(100, 7));
end.
