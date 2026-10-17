unit StringLength;

interface

function TextLength(Value: String): Integer;

implementation

function TextLength(Value: String): Integer;
begin
  Result := Length(Value);
end;

end.
