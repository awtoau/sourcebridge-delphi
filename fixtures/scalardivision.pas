unit ScalarDivision;

{$mode objfpc}{$H+}

interface

function DivSigned(Left: Integer; Right: Integer): Integer;
function DivUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;

implementation

function DivSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left div Right;
end;

function DivUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left div Right;
end;

end.
