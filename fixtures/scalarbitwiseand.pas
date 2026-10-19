unit ScalarBitwiseAnd;

{$mode objfpc}{$H+}

interface

function BitAndSigned(Left: Integer; Right: Integer): Integer;
function BitAndUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;

implementation

function BitAndSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left and Right;
end;

function BitAndUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left and Right;
end;

end.
