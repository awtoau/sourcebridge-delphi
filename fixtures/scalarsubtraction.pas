unit ScalarSubtraction;

{$mode objfpc}{$H+}

interface

function SubSigned(Left: Integer; Right: Integer): Integer;
function SubUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;

implementation

function SubSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left - Right;
end;

function SubUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left - Right;
end;

end.
