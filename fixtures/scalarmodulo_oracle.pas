program ScalarModuloOracle;

{$mode objfpc}{$H+}

function ModSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left mod Right;
end;

function ModUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left mod Right;
end;

begin
  Writeln('modsigned(-7,2)=', ModSigned(-7, 2));
  Writeln('modsigned(7,3)=', ModSigned(7, 3));
  Writeln('modunsigned(100,7)=', ModUnsigned(100, 7));
end.
