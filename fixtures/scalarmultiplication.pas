unit ScalarMultiplication;

{$mode objfpc}{$H+}

interface

function MulSigned(Left: Integer; Right: Integer): Integer;
function MulUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;

implementation

function MulSigned(Left: Integer; Right: Integer): Integer;
begin
  Result := Left * Right;
end;

function MulUnsigned(Left: Cardinal; Right: Cardinal): Cardinal;
begin
  Result := Left * Right;
end;

end.
