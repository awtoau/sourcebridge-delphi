unit BooleanExpression;

interface

function IsGreater(Left: Integer; Right: Integer): Boolean;

implementation

function IsGreater(Left: Integer; Right: Integer): Boolean;
begin
  Result := Left > Right;
end;

end.
