unit ScalarModulo;

{$mode objfpc}{$H+}

interface

function ModSigned(Left: Integer; Right: Integer): Integer;
function ModUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;

implementation

function ModSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left mod Right;
end;

function ModUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left mod Right;
end;

end.
