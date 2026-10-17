unit BooleanComparison;

interface

function IsGreater(Left: Integer; Right: Integer): Boolean;

implementation

function IsGreater(Left: Integer; Right: Integer): Boolean;
begin
  if Left > Right then
    Result := True
  else
    Result := False;
end;

end.
